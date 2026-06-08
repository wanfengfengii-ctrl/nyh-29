import streamlit as st

from core import navigate_to, render_page_header
from core.validators import FormValidator, validate_required, validate_positive_number
from db import (
    get_default_sieve_sizes,
    get_all_groups,
    get_sample_by_no,
    add_sample,
    batch_add_sieve_data,
)
from analysis import validate_sieve_data, get_sieve_label


def _render_sieve_inputs(default_sieves, key_prefix="sieve"):
    sieve_weights = {}
    sieve_cols = st.columns(3)
    for i, size in enumerate(default_sieves):
        label = get_sieve_label(size)
        col_idx = i % 3
        with sieve_cols[col_idx]:
            sieve_weights[size] = st.number_input(
                f"{label} 留存重量 (g)",
                min_value=0.0,
                step=0.01,
                value=0.0,
                key=f"{key_prefix}_{size}"
            )
    return sieve_weights


def render_new_sample():
    render_page_header("➕ 新建火山灰样本")
    
    default_sieves = get_default_sieve_sizes()
    all_groups = get_all_groups()
    
    with st.form("new_sample_form"):
        st.subheader("基本信息")
        col1, col2 = st.columns(2)
        with col1:
            sample_no = st.text_input("样本编号 *", help="样本编号不能重复")
            sampling_site = st.text_input("采样点 *")
            eruption_layer = st.text_input("喷发层位")
            group_options = ["（新建分组）"] + all_groups if all_groups else ["（新建分组）"]
            group_choice = st.selectbox("分组", group_options, 
                                       help="选择已有分组或新建分组")
            if group_choice == "（新建分组）":
                group_name = st.text_input("新建分组名称", "")
            else:
                group_name = group_choice
        
        with col2:
            total_weight = st.number_input("样本总重量 (g) *", min_value=0.0, step=0.1, value=100.0)
            sampling_time = st.text_input("采样时间", value="", 
                                          help="格式: YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")
            depth = st.number_input("采样深度 (m)", min_value=0.0, step=0.1, value=0.0,
                                   help="样本在剖面中的深度")
            profile_position = st.text_input("剖面位置", value="", 
                                            help="如：剖面A、剖面B 等")
        
        col3, col4 = st.columns(2)
        with col3:
            latitude = st.number_input("纬度", value=0.0, step=0.0001, format="%.4f")
        with col4:
            longitude = st.number_input("经度", value=0.0, step=0.0001, format="%.4f")
        
        description = st.text_area("备注", height=80)
        
        st.markdown("---")
        st.subheader("筛分数据 (各粒级留存重量)")
        st.caption("填写各粒级留存重量（g），未填或填 0 表示该粒级无数据")
        
        sieve_weights = _render_sieve_inputs(default_sieves)
        
        submitted = st.form_submit_button("保存样本", type="primary", use_container_width=True)
        
        if submitted:
            validator = FormValidator()
            
            validator.validate(validate_required(sample_no, "样本编号"))
            validator.validate(validate_required(sampling_site, "采样点"))
            validator.validate(validate_positive_number(total_weight, "总重量", min_value=0, allow_zero=False))
            
            if not validator.is_valid:
                validator.show_errors()
                return
            
            existing = get_sample_by_no(sample_no.strip())
            if existing:
                st.error(f"样本编号 {sample_no} 已存在，请使用其他编号")
                return
            
            sieve_data_list = [(size, weight) for size, weight in sieve_weights.items() if weight > 0]
            
            valid, msg = validate_sieve_data(
                [{'sieve_size': s, 'retained_weight': w} for s, w in sieve_data_list],
                total_weight
            )
            if not valid:
                st.error(msg)
                return
            
            sample_id = add_sample(
                sample_no=sample_no.strip(),
                sampling_site=sampling_site.strip(),
                eruption_layer=eruption_layer.strip(),
                total_weight=total_weight,
                description=description.strip(),
                group_name=group_name.strip() if group_name and group_name.strip() else None,
                sampling_time=sampling_time.strip() if sampling_time.strip() else None,
                depth=depth if depth > 0 else None,
                profile_position=profile_position.strip() if profile_position.strip() else None,
                latitude=latitude if latitude != 0 else None,
                longitude=longitude if longitude != 0 else None,
            )
            
            if sieve_data_list:
                batch_add_sieve_data(sample_id, sieve_data_list)
            
            st.success(f"样本 {sample_no} 创建成功！")
            navigate_to("查看样本", viewing_sample_id=sample_id)
