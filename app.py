import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
from datetime import datetime

from db import (
    init_db,
    get_all_samples,
    get_sample,
    get_sample_by_no,
    add_sample,
    update_sample,
    delete_sample,
    batch_delete_samples,
    batch_add_sieve_data,
    get_default_sieve_sizes,
    get_all_groups,
    get_samples_by_group,
    get_operation_logs,
    batch_import_samples,
)
from analysis import (
    calculate_analysis,
    validate_sieve_data,
    get_sieve_label,
    generate_export_data,
    generate_summary_export,
    suggest_missing_sieve_fill,
    get_reliability_color,
    prepare_profile_analysis,
    generate_trend_analysis,
)
from report import (
    generate_pdf_report,
    generate_word_report,
    get_import_template_csv,
    parse_import_csv,
)

st.set_page_config(
    page_title="火山灰样本分析系统",
    page_icon="🌋",
    layout="wide",
)

init_db()

if "current_page" not in st.session_state:
    st.session_state.current_page = "样本列表"
if "editing_sample_id" not in st.session_state:
    st.session_state.editing_sample_id = None
if "viewing_sample_id" not in st.session_state:
    st.session_state.viewing_sample_id = None
if "confirm_delete_id" not in st.session_state:
    st.session_state.confirm_delete_id = None
if "batch_delete_ids" not in st.session_state:
    st.session_state.batch_delete_ids = []


def navigate_to(page, **kwargs):
    st.session_state.current_page = page
    for key, value in kwargs.items():
        st.session_state[key] = value
    st.session_state.confirm_delete_id = None
    st.session_state.batch_delete_ids = []
    st.rerun()


def render_sidebar():
    with st.sidebar:
        st.title("🌋 火山灰分析系统")
        st.markdown("---")
        
        nav_items = [
            ("📋 样本列表", "样本列表"),
            ("➕ 新建样本", "新建样本"),
            ("📥 批量导入", "批量导入"),
            ("📊 样本对比", "样本对比"),
            ("📈 剖面分析", "剖面分析"),
            ("📄 操作日志", "操作日志"),
        ]
        
        for label, page in nav_items:
            is_active = st.session_state.current_page == page
            if st.button(label, use_container_width=True, type="primary" if is_active else "secondary"):
                navigate_to(page)
        
        st.markdown("---")
        st.caption("地质实验室 · 火山灰筛分分析")


def render_sample_list():
    st.header("📋 火山灰样本列表")
    
    samples = get_all_samples()
    
    if not samples:
        st.info("暂无样本数据，点击左侧「新建样本」开始录入。")
        return
    
    all_groups = get_all_groups()
    
    col_filter1, col_filter2 = st.columns([1, 1])
    with col_filter1:
        if all_groups:
            group_filter = st.selectbox(
                "按分组筛选",
                ["全部"] + all_groups,
                index=0,
            )
            if group_filter != "全部":
                samples = [s for s in samples if s.get('group_name') == group_filter]
        else:
            st.caption("暂无分组数据")
    
    with col_filter2:
        search_text = st.text_input("搜索样本编号/采样点", "")
        if search_text.strip():
            search = search_text.strip().lower()
            samples = [s for s in samples 
                      if search in s['sample_no'].lower() 
                      or search in s['sampling_site'].lower()]
    
    df = pd.DataFrame(samples)
    
    display_df = df[['sample_no', 'sampling_site', 'eruption_layer', 'group_name', 
                     'total_weight', 'sieve_count', 'depth', 'sampling_time', 'created_at']].copy()
    display_df.columns = ['样本编号', '采样点', '喷发层位', '分组', '总重量(g)', 
                          '粒级数', '深度(m)', '采样时间', '创建时间']
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.markdown("### 操作")
    
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    
    with col1:
        sample_options = {f"{s['sample_no']} - {s['sampling_site']}": s['id'] for s in samples}
        selected = st.selectbox("选择样本", list(sample_options.keys()), label_visibility="collapsed")
        selected_id = sample_options[selected]
    
    with col2:
        if st.button("查看详情", use_container_width=True):
            navigate_to("查看样本", viewing_sample_id=selected_id)
    
    with col3:
        if st.button("✏️ 编辑", use_container_width=True):
            navigate_to("查看样本", viewing_sample_id=selected_id)
    
    with col4:
        if st.session_state.confirm_delete_id == selected_id:
            st.warning("⚠️ 确认删除？此操作不可恢复！")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("确认删除", type="primary", use_container_width=True):
                    delete_sample(selected_id)
                    st.success("样本已删除")
                    st.session_state.confirm_delete_id = None
                    st.rerun()
            with col_no:
                if st.button("取消", use_container_width=True):
                    st.session_state.confirm_delete_id = None
                    st.rerun()
        else:
            if st.button("🗑️ 删除样本", use_container_width=True, type="secondary"):
                st.session_state.confirm_delete_id = selected_id
                st.rerun()
    
    st.markdown("---")
    st.subheader("批量操作")
    
    selected_for_batch = st.multiselect(
        "选择要批量删除的样本",
        [f"{s['sample_no']} - {s['sampling_site']}" for s in samples],
        default=[],
    )
    
    if selected_for_batch:
        batch_ids = [sample_options[s] for s in selected_for_batch]
        
        if st.session_state.batch_delete_ids == batch_ids:
            st.error(f"⚠️ 确认删除 {len(batch_ids)} 个样本？此操作不可恢复！")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("确认批量删除", type="primary", use_container_width=True):
                    count = batch_delete_samples(batch_ids)
                    st.success(f"已成功删除 {count} 个样本")
                    st.session_state.batch_delete_ids = []
                    st.rerun()
            with col_no:
                if st.button("取消", use_container_width=True):
                    st.session_state.batch_delete_ids = []
                    st.rerun()
        else:
            if st.button("批量删除选中样本", type="secondary"):
                st.session_state.batch_delete_ids = batch_ids
                st.rerun()


def render_new_sample():
    st.header("➕ 新建火山灰样本")
    
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
                    key=f"sieve_{size}"
                )
        
        submitted = st.form_submit_button("保存样本", type="primary", use_container_width=True)
        
        if submitted:
            if not sample_no.strip():
                st.error("请输入样本编号")
                return
            if not sampling_site.strip():
                st.error("请输入采样点")
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


def render_view_sample():
    sample_id = st.session_state.viewing_sample_id
    sample = get_sample(sample_id)
    
    if not sample:
        st.error("样本不存在")
        return
    
    col1, col2 = st.columns([4, 1])
    with col1:
        st.header(f"🔬 样本详情 - {sample['sample_no']}")
    with col2:
        if st.button("返回列表", use_container_width=True):
            navigate_to("样本列表")
    
    default_sieves = get_default_sieve_sizes()
    existing_sieves = {d['sieve_size']: d['retained_weight'] for d in sample['sieve_data']}
    analysis = calculate_analysis(sample['sieve_data'], sample['total_weight'])
    
    with st.expander("基本信息", expanded=True):
        info_cols = st.columns(4)
        with info_cols[0]:
            st.metric("样本编号", sample['sample_no'])
        with info_cols[1]:
            st.metric("采样点", sample['sampling_site'])
        with info_cols[2]:
            st.metric("喷发层位", sample.get('eruption_layer') or '未记录')
        with info_cols[3]:
            st.metric("总重量", f"{sample['total_weight']:.2f} g")
        
        info_cols2 = st.columns(4)
        with info_cols2[0]:
            st.metric("分组", sample.get('group_name') or '未分组')
        with info_cols2[1]:
            st.metric("采样时间", sample.get('sampling_time') or '未记录')
        with info_cols2[2]:
            depth_val = f"{sample['depth']:.2f} m" if sample.get('depth') else '未记录'
            st.metric("采样深度", depth_val)
        with info_cols2[3]:
            st.metric("剖面位置", sample.get('profile_position') or '未记录')
        
        if sample.get('latitude') and sample.get('longitude'):
            st.caption(f"经纬度：{sample['latitude']:.4f}, {sample['longitude']:.4f}")
        
        if sample['description']:
            st.markdown(f"**备注：** {sample['description']}")
    
    with st.expander("✏️ 编辑基础信息", expanded=False):
        all_groups = get_all_groups()
        with st.form("edit_basic_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_sample_no = st.text_input("样本编号 *", value=sample['sample_no'])
                new_sampling_site = st.text_input("采样点 *", value=sample['sampling_site'])
                new_eruption_layer = st.text_input("喷发层位", value=sample.get('eruption_layer') or '')
                
                group_options = ["（新建分组）"] + all_groups if all_groups else ["（新建分组）"]
                current_group = sample.get('group_name') or ''
                if current_group and current_group in group_options:
                    default_group_idx = group_options.index(current_group)
                else:
                    default_group_idx = 0
                group_choice = st.selectbox("分组", group_options, index=default_group_idx)
                if group_choice == "（新建分组）":
                    new_group_name = st.text_input("新建分组名称", value=current_group)
                else:
                    new_group_name = group_choice
            
            with col2:
                new_total_weight = st.number_input(
                    "样本总重量 (g) *",
                    min_value=0.0,
                    step=0.1,
                    value=float(sample['total_weight'])
                )
                new_sampling_time = st.text_input(
                    "采样时间",
                    value=sample.get('sampling_time') or '',
                    help="格式: YYYY-MM-DD"
                )
                new_depth = st.number_input(
                    "采样深度 (m)",
                    min_value=0.0,
                    step=0.1,
                    value=float(sample.get('depth') or 0)
                )
                new_profile_position = st.text_input(
                    "剖面位置",
                    value=sample.get('profile_position') or ''
                )
            
            col3, col4 = st.columns(2)
            with col3:
                new_latitude = st.number_input(
                    "纬度",
                    value=float(sample.get('latitude') or 0),
                    step=0.0001,
                    format="%.4f"
                )
            with col4:
                new_longitude = st.number_input(
                    "经度",
                    value=float(sample.get('longitude') or 0),
                    step=0.0001,
                    format="%.4f"
                )
            
            new_description = st.text_area(
                "备注",
                value=sample.get('description') or '',
                height=80
            )
            
            edit_basic_submitted = st.form_submit_button("保存修改", type="primary", use_container_width=True)
            
            if edit_basic_submitted:
                if not new_sample_no.strip():
                    st.error("请输入样本编号")
                elif not new_sampling_site.strip():
                    st.error("请输入采样点")
                else:
                    existing = get_sample_by_no(new_sample_no.strip())
                    if existing and existing['id'] != sample['id']:
                        st.error(f"样本编号 {new_sample_no} 已被其他样本使用，请使用其他编号")
                    else:
                        total_sieved = sum(d['retained_weight'] for d in sample['sieve_data'])
                        if total_sieved > new_total_weight + 0.001:
                            st.error(f"修改后总重量 ({new_total_weight:.2f} g) 小于现有筛分总重量 ({total_sieved:.2f} g)，请先调整筛分数据")
                        else:
                            update_sample(
                                sample_id=sample['id'],
                                sample_no=new_sample_no.strip(),
                                sampling_site=new_sampling_site.strip(),
                                eruption_layer=new_eruption_layer.strip(),
                                total_weight=new_total_weight,
                                description=new_description.strip(),
                                group_name=new_group_name.strip() if new_group_name and new_group_name.strip() else None,
                                sampling_time=new_sampling_time.strip() if new_sampling_time.strip() else None,
                                depth=new_depth if new_depth > 0 else None,
                                profile_position=new_profile_position.strip() if new_profile_position.strip() else None,
                                latitude=new_latitude if new_latitude != 0 else None,
                                longitude=new_longitude if new_longitude != 0 else None,
                            )
                            st.success("基础信息已更新！")
                            st.rerun()
    
    with st.expander("📊 筛分分析结果", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            d50_val = f"{analysis['median_diameter']:.3f} mm" if analysis['median_diameter'] else "—"
            st.metric("中值粒径 (D50)", d50_val)
        with col2:
            sc_val = f"{analysis['sorting_coefficient']:.2f}" if analysis['sorting_coefficient'] else "—"
            st.metric("分选系数", sc_val)
        with col3:
            grade = analysis['sorting_grade']
            st.metric("沉积分选评价", grade)
        with col4:
            retained_pct = analysis['total_retained'] / sample['total_weight'] * 100 if sample['total_weight'] > 0 else 0
            st.metric("筛分回收率", f"{retained_pct:.1f}%")
        
        reliab_color = get_reliability_color(analysis['reliability_level'])
        col_r1, col_r2 = st.columns([1, 3])
        with col_r1:
            st.metric(
                "分析可信度",
                f"{analysis['reliability_score']:.0f}/100 ({analysis['reliability_level']})",
            )
        with col_r2:
            st.caption("可信度评估说明：")
            details = analysis.get('reliability_details', {})
            for key, detail in details.items():
                st.caption(f"• {detail['description']} — 得分: {detail['score']}/{detail['max_score']}")
        
        st.markdown("#### 粒径参数")
        col_d = st.columns(5)
        d_params = [
            ("D10", analysis['d10']),
            ("D25", analysis['d25']),
            ("D50", analysis['median_diameter']),
            ("D75", analysis['d75']),
            ("D90", analysis['d90']),
        ]
        for i, (name, val) in enumerate(d_params):
            with col_d[i]:
                display_val = f"{val:.3f} mm" if val else "—"
                st.caption(f"{name}")
                st.markdown(f"**{display_val}**")
    
    missing_sieves = [s for s in default_sieves if s not in existing_sieves]
    suggestions = suggest_missing_sieve_fill(sample['sieve_data'], default_sieves)
    
    if missing_sieves:
        with st.expander("💡 缺失粒级智能补全建议", expanded=True):
            st.info(f"⚠️ 当前缺失 {len(missing_sieves)} 个粒级数据")
            
            if suggestions:
                st.markdown("#### 智能插值建议")
                st.caption("基于相邻粒级数据的对数插值估算，仅供参考")
                
                sugg_df = pd.DataFrame(suggestions)
                if not sugg_df.empty:
                    sugg_df = sugg_df[['sieve_label', 'suggested_weight', 'confidence']]
                    sugg_df.columns = ['粒级', '建议重量 (g)', '可信度']
                    sugg_df['可信度'] = sugg_df['可信度'].map({
                        'high': '高', 'medium': '中', 'low': '低'
                    })
                    st.dataframe(sugg_df, use_container_width=True, hide_index=True)
                
                st.caption("注：以上为算法估算值，实际数据请以实验测量为准")
    
    with st.expander("📋 筛分数据明细", expanded=True):
        df_display = analysis['df'].copy()
        if not df_display.empty:
            df_display['粒级'] = df_display['sieve_size'].apply(get_sieve_label)
            df_display = df_display[['粒级', 'sieve_size', 'retained_weight', 'weight_percent']]
            df_display.columns = ['粒级', '筛孔(mm)', '留存重量(g)', '占比(%)']
            
            cum_df_display = analysis['cum_df'].copy()
            cum_df_display = cum_df_display[cum_df_display['sieve_size'] <= df_display['筛孔(mm)'].max()]
            cum_df_display['筛孔(mm)'] = cum_df_display['sieve_size']
            cum_df_display['小于该筛孔累计(%)'] = cum_df_display['cumulative_percent']
            cum_df_display = cum_df_display[['筛孔(mm)', '小于该筛孔累计(%)']]
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**各粒级留存**")
                st.dataframe(df_display, use_container_width=True, hide_index=True)
            with col2:
                st.markdown("**累计分布（小于该粒径）**")
                st.dataframe(cum_df_display, use_container_width=True, hide_index=True)
            
            if analysis.get('pan_weight', 0) > 0:
                st.caption(f"底盘（小于最小粒级）重量：{analysis['pan_weight']:.4f} g ({analysis['pan_percent']:.2f}%)")
        else:
            st.info("暂无筛分数据")
    
    with st.expander("📈 粒径分布图", expanded=True):
        if analysis['df'].empty:
            st.info("暂无筛分数据，无法生成图表")
        else:
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.08,
                subplot_titles=("粒径分布直方图", "累计粒径分布曲线（小于某粒径累计%）")
            )
            
            fig.add_trace(
                go.Bar(
                    x=analysis['df']['sieve_size'],
                    y=analysis['df']['weight_percent'],
                    name='粒级占比',
                    marker_color='steelblue',
                    hovertemplate='粒级: %{x} mm<br>占比: %{y:.2f}%<extra></extra>'
                ),
                row=1, col=1
            )
            
            cum_df = analysis['cum_df']
            fig.add_trace(
                go.Scatter(
                    x=cum_df['sieve_size'],
                    y=cum_df['cumulative_percent'],
                    mode='lines+markers',
                    name='累计百分比',
                    line=dict(color='crimson', width=2),
                    marker=dict(size=6),
                    hovertemplate='粒径: %{x:.3f} mm<br>小于该粒径累计: %{y:.2f}%<extra></extra>'
                ),
                row=2, col=1
            )
            
            if analysis['median_diameter']:
                fig.add_hline(
                    y=50, line_dash="dash", line_color="gray",
                    annotation_text="D50=50%",
                    row=2, col=1
                )
                fig.add_vline(
                    x=analysis['median_diameter'], line_dash="dash", line_color="green",
                    annotation_text=f"D50={analysis['median_diameter']:.3f}mm",
                    row=2, col=1
                )
            
            fig.update_xaxes(type="log", title_text="粒径 (mm)", row=2, col=1)
            fig.update_yaxes(title_text="重量百分比 (%)", row=1, col=1)
            fig.update_yaxes(title_text="累计百分比 (%)", range=[0, 105], row=2, col=1)
            fig.update_layout(
                height=600,
                showlegend=False,
                hovermode="x unified"
            )
            
            st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    st.subheader("✏️ 编辑筛分数据")
    st.caption("修改后点击「保存更新」，所有统计结果将自动重新计算")
    
    with st.form("edit_sieve_form"):
        sieve_weights = {}
        sieve_cols = st.columns(3)
        for i, size in enumerate(default_sieves):
            label = get_sieve_label(size)
            current_val = existing_sieves.get(size, 0.0)
            col_idx = i % 3
            with sieve_cols[col_idx]:
                sieve_weights[size] = st.number_input(
                    f"{label} 留存重量 (g)",
                    min_value=0.0,
                    step=0.01,
                    value=float(current_val),
                    key=f"edit_sieve_{size}"
                )
        
        edit_submitted = st.form_submit_button("保存更新", type="primary", use_container_width=True)
        
        if edit_submitted:
            sieve_data_list = [(size, weight) for size, weight in sieve_weights.items() if weight > 0]
            
            valid, msg = validate_sieve_data(
                [{'sieve_size': s, 'retained_weight': w} for s, w in sieve_data_list],
                sample['total_weight']
            )
            if not valid:
                st.error(msg)
                st.stop()
            
            batch_add_sieve_data(sample_id, sieve_data_list)
            st.success("筛分数据已更新！")
            st.rerun()
    
    st.markdown("---")
    st.subheader("📥 数据导出")
    
    export_cols = st.columns(4)
    
    with export_cols[0]:
        if not analysis['df'].empty:
            export_df = generate_export_data([{**sample, 'analysis': analysis}])
            csv = export_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📄 详细 CSV",
                data=csv,
                file_name=f"样本_{sample['sample_no']}_筛分明细.csv",
                mime='text/csv',
                use_container_width=True
            )
    
    with export_cols[1]:
        if not analysis['df'].empty:
            summary_df = generate_summary_export([{**sample, 'analysis': analysis}])
            csv = summary_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📊 汇总 CSV",
                data=csv,
                file_name=f"样本_{sample['sample_no']}_分析汇总.csv",
                mime='text/csv',
                use_container_width=True
            )
    
    sample_data_for_report = [{**sample, 'analysis': analysis}]
    
    with export_cols[2]:
        try:
            pdf_data = generate_pdf_report(sample_data_for_report, 
                                          title=f"火山灰样本 {sample['sample_no']} 分析报告")
            st.download_button(
                "📕 PDF 报告",
                data=pdf_data,
                file_name=f"样本_{sample['sample_no']}_分析报告.pdf",
                mime='application/pdf',
                use_container_width=True
            )
        except ImportError:
            if st.button("📕 PDF 报告", use_container_width=True, disabled=True):
                pass
            st.caption("请安装 reportlab: pip install reportlab")
    
    with export_cols[3]:
        try:
            word_data = generate_word_report(sample_data_for_report,
                                            title=f"火山灰样本 {sample['sample_no']} 分析报告")
            st.download_button(
                "📘 Word 报告",
                data=word_data,
                file_name=f"样本_{sample['sample_no']}_分析报告.docx",
                mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                use_container_width=True
            )
        except ImportError:
            if st.button("📘 Word 报告", use_container_width=True, disabled=True):
                pass
            st.caption("请安装 python-docx: pip install python-docx")


def render_comparison():
    st.header("📊 多样本对比分析")
    
    samples = get_all_samples()
    
    if len(samples) < 2:
        st.info("至少需要 2 个样本才能进行对比，请先创建更多样本。")
        return
    
    all_groups = get_all_groups()
    if all_groups:
        group_select = st.selectbox(
            "按分组快速选择",
            ["全部样本"] + all_groups,
            index=0,
            key="comp_group_select"
        )
        if group_select != "全部样本":
            group_samples = get_samples_by_group(group_select)
            default_selected = [f"{s['sample_no']} - {s['sampling_site']}" for s in group_samples]
        else:
            default_selected = list(samples.keys())[:3] if len(samples) >= 3 else list(samples.keys())
    else:
        default_selected = list(samples.keys())[:3] if len(samples) >= 3 else list(samples.keys())
    
    sample_options = {f"{s['sample_no']} - {s['sampling_site']}": s['id'] for s in samples}
    selected_labels = st.multiselect(
        "选择要对比的样本（至少2个）",
        list(sample_options.keys()),
        default=default_selected if len(default_selected) >= 2 else list(sample_options.keys())[:2]
    )
    
    if len(selected_labels) < 2:
        st.warning("请至少选择 2 个样本进行对比")
        return
    
    selected_ids = [sample_options[label] for label in selected_labels]
    samples_data = []
    for sid in selected_ids:
        sample = get_sample(sid)
        if sample:
            analysis = calculate_analysis(sample['sieve_data'], sample['total_weight'])
            samples_data.append({**sample, 'analysis': analysis})
    
    st.markdown("### 对比汇总表")
    summary_df = generate_summary_export(samples_data)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
    
    default_sieves = get_default_sieve_sizes()
    
    st.markdown("### 累计粒径分布对比")
    st.caption("曲线表示「小于该粒径的颗粒质量累计百分比」")
    
    fig = go.Figure()
    
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    missing_info = []
    for i, sample in enumerate(samples_data):
        analysis = sample['analysis']
        existing_sieves = {d['sieve_size'] for d in sample['sieve_data']}
        missing_sieves = [s for s in default_sieves if s not in existing_sieves]
        if missing_sieves:
            missing_labels = [get_sieve_label(s) for s in sorted(missing_sieves)]
            missing_info.append(f"{sample['sample_no']} 缺失: {', '.join(missing_labels)}")
        
        if not analysis['cum_df'].empty:
            color = colors[i % len(colors)]
            cum_df = analysis['cum_df']
            fig.add_trace(
                go.Scatter(
                    x=cum_df['sieve_size'],
                    y=cum_df['cumulative_percent'],
                    mode='lines+markers',
                    name=sample['sample_no'],
                    line=dict(width=2, color=color),
                    marker=dict(size=6),
                    hovertemplate=f"{sample['sample_no']}<br>粒径: %{{x:.3f}} mm<br>小于该粒径累计: %{{y:.2f}}%<extra></extra>"
                )
            )
    
    fig.update_xaxes(type="log", title_text="粒径 (mm)")
    fig.update_yaxes(title_text="小于该粒径累计 (%)", range=[0, 105])
    fig.update_layout(
        height=500,
        legend_title="样本编号",
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    if missing_info:
        st.warning("⚠️ 部分样本缺失粒级数据：\n\n" + "\n\n".join(missing_info))
    
    st.markdown("### 粒径分布直方图对比")
    
    fig2 = go.Figure()
    
    for i, sample in enumerate(samples_data):
        analysis = sample['analysis']
        if not analysis['df'].empty:
            color = colors[i % len(colors)]
            fig2.add_trace(
                go.Bar(
                    x=analysis['df']['sieve_size'],
                    y=analysis['df']['weight_percent'],
                    name=sample['sample_no'],
                    marker_color=color,
                    opacity=0.7,
                    hovertemplate=f"{sample['sample_no']}<br>粒级: %{{x}} mm<br>占比: %{{y:.2f}}%<extra></extra>"
                )
            )
    
    fig2.update_xaxes(type="log", title_text="粒径 (mm)")
    fig2.update_yaxes(title_text="重量百分比 (%)")
    fig2.update_layout(
        height=450,
        barmode='group',
        legend_title="样本编号"
    )
    
    st.plotly_chart(fig2, use_container_width=True)
    
    st.markdown("### 📥 导出对比数据")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        export_detail = generate_export_data(samples_data)
        csv_detail = export_detail.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📄 详细数据 CSV",
            data=csv_detail,
            file_name="多样本筛分对比_明细.csv",
            mime='text/csv',
            use_container_width=True
        )
    
    with col2:
        summary_export = generate_summary_export(samples_data)
        csv_summary = summary_export.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📊 汇总对比 CSV",
            data=csv_summary,
            file_name="多样本筛分对比_汇总.csv",
            mime='text/csv',
            use_container_width=True
        )
    
    with col3:
        try:
            pdf_data = generate_pdf_report(samples_data, title="火山灰多样本对比分析报告")
            st.download_button(
                "📕 PDF 对比报告",
                data=pdf_data,
                file_name="多样本对比分析报告.pdf",
                mime='application/pdf',
                use_container_width=True
            )
        except ImportError:
            st.caption("请安装 reportlab 以导出 PDF")
    
    with col4:
        try:
            word_data = generate_word_report(samples_data, title="火山灰多样本对比分析报告")
            st.download_button(
                "📘 Word 对比报告",
                data=word_data,
                file_name="多样本对比分析报告.docx",
                mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                use_container_width=True
            )
        except ImportError:
            st.caption("请安装 python-docx 以导出 Word")


def render_batch_import():
    st.header("📥 批量导入样本")
    
    st.markdown("### 1. 下载导入模板")
    template_csv = get_import_template_csv()
    st.download_button(
        "📄 下载 CSV 模板",
        data=template_csv.encode('utf-8-sig'),
        file_name="火山灰样本批量导入模板.csv",
        mime='text/csv',
        use_container_width=True,
    )
    
    with st.expander("📖 导入格式说明", expanded=False):
        st.markdown("""
        **CSV 文件格式说明：**
        
        **必填字段：**
        - 样本编号：唯一标识，不能重复
        - 采样点：采样地点名称
        - 总重量(g)：样本总重量，数值
        
        **可选字段：**
        - 喷发层位：地质层位信息
        - 备注：其他说明
        - 分组：样本所属分组，用于批量管理
        - 采样时间：格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS
        - 深度(m)：采样深度，数值
        - 剖面位置：剖面编号/名称
        - 纬度、经度：坐标信息
        
        **粒级数据列：**
        - 列名格式：`粒级_Xmm_重量(g)`，X 为筛孔尺寸
        - 填写对应粒级的留存重量（g），为空或 0 表示无数据
        - 示例：`粒级_2.0mm_重量(g)`
        """)
    
    st.markdown("### 2. 上传 CSV 文件")
    
    uploaded_file = st.file_uploader(
        "选择 CSV 文件",
        type=['csv'],
        help="支持 UTF-8 编码的 CSV 文件"
    )
    
    if uploaded_file is not None:
        try:
            content = uploaded_file.read().decode('utf-8-sig')
            samples_data = parse_import_csv(content)
            
            if not samples_data:
                st.error("未解析到有效数据，请检查文件格式")
                return
            
            st.success(f"成功解析 {len(samples_data)} 条样本数据")
            
            st.markdown("### 3. 数据预览")
            
            preview_rows = []
            for s in samples_data:
                preview_rows.append({
                    '样本编号': s.get('sample_no', ''),
                    '采样点': s.get('sampling_site', ''),
                    '总重量': s.get('total_weight', ''),
                    '分组': s.get('group_name', ''),
                    '粒级数': len(s.get('sieve_data', [])),
                })
            
            preview_df = pd.DataFrame(preview_rows)
            st.dataframe(preview_df, use_container_width=True, hide_index=True)
            
            st.markdown("### 4. 确认导入")
            
            st.warning("⚠️ 导入操作将创建新样本，样本编号已存在的会被跳过")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                confirm_import = st.checkbox("我已确认数据无误，确认导入")
            
            with col2:
                if confirm_import:
                    if st.button("开始导入", type="primary", use_container_width=True):
                        with st.spinner("正在导入..."):
                            success, failed, errors = batch_import_samples(samples_data)
                        
                        st.success(f"导入完成：成功 {success} 条，失败 {failed} 条")
                        
                        if errors:
                            st.error("失败详情：")
                            for err in errors:
                                st.caption(f"• {err}")
                        
                        if success > 0:
                            st.info("3秒后跳转到样本列表...")
                            st.session_state.current_page = "样本列表"
                            st.rerun()
                else:
                    st.button("开始导入", disabled=True, use_container_width=True)
        
        except Exception as e:
            st.error(f"文件解析失败：{str(e)}")


def render_profile_analysis():
    st.header("📈 时间序列/剖面对比分析")
    
    samples = get_all_samples()
    
    if len(samples) < 2:
        st.info("至少需要 2 个样本才能进行剖面/时间序列分析。")
        return
    
    all_groups = get_all_groups()
    
    col1, col2 = st.columns(2)
    with col1:
        analysis_type = st.radio(
            "分析类型",
            ["深度剖面分析", "时间序列分析"],
            horizontal=True,
        )
    
    with col2:
        if all_groups:
            group_filter = st.selectbox(
                "选择分组",
                ["全部"] + all_groups,
                index=0,
            )
            if group_filter != "全部":
                samples = [s for s in samples if s.get('group_name') == group_filter]
        else:
            st.caption("暂无分组数据，建议先对样本设置分组以便更好地分析")
    
    samples_data = []
    for sample in samples:
        analysis = calculate_analysis(sample['sieve_data'], sample['total_weight'])
        samples_data.append({**sample, 'analysis': analysis})
    
    sort_by = 'depth' if analysis_type == "深度剖面分析" else 'time'
    profile_df = prepare_profile_analysis(samples_data, sort_by=sort_by)
    
    if profile_df.empty or len(profile_df) < 2:
        field_name = "深度" if sort_by == 'depth' else "采样时间"
        st.warning(f"样本中有效 {field_name} 数据不足 2 个，请先为样本设置 {field_name}")
        return
    
    st.markdown(f"### {analysis_type}数据总览")
    
    display_df = profile_df.copy()
    
    if sort_by == 'depth':
        display_df = display_df[['sample_no', 'depth', 'D10', 'D25', 'D50', 'D75', 'D90', 
                                'sorting_coefficient', 'sorting_grade', 'reliability_score']]
        display_df.columns = ['样本编号', '深度(m)', 'D10(mm)', 'D25(mm)', 'D50(mm)', 'D75(mm)', 
                              'D90(mm)', '分选系数', '分选等级', '可信度']
    else:
        display_df = display_df[['sample_no', 'sampling_time', 'D10', 'D25', 'D50', 'D75', 'D90',
                                'sorting_coefficient', 'sorting_grade', 'reliability_score']]
        display_df.columns = ['样本编号', '采样时间', 'D10(mm)', 'D25(mm)', 'D50(mm)', 'D75(mm)',
                              'D90(mm)', '分选系数', '分选等级', '可信度']
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.markdown("### 粒径参数趋势图")
    
    param_options = ['D50', 'D10', 'D25', 'D75', 'D90', 'sorting_coefficient']
    param_labels = {
        'D50': '中值粒径 D50 (mm)',
        'D10': 'D10 (mm)',
        'D25': 'D25 (mm)',
        'D75': 'D75 (mm)',
        'D90': 'D90 (mm)',
        'sorting_coefficient': '分选系数',
    }
    
    selected_param = st.selectbox(
        "选择参数",
        param_options,
        format_func=lambda x: param_labels[x],
        index=0,
    )
    
    x_label = '深度 (m)' if sort_by == 'depth' else '采样时间'
    x_values = profile_df['depth'].values if sort_by == 'depth' else profile_df.index.values
    x_tick_text = profile_df['depth'].astype(str).values if sort_by == 'depth' else profile_df['sampling_time'].values
    
    y_values = profile_df[selected_param].values
    
    fig = go.Figure()
    
    fig.add_trace(
        go.Scatter(
            x=list(range(len(y_values))),
            y=y_values,
            mode='lines+markers',
            name=param_labels[selected_param],
            line=dict(width=3, color='#1f77b4'),
            marker=dict(size=10, color='#1f77b4'),
            text=profile_df['sample_no'].values,
            hovertemplate=(
                f"样本: %{{text}}<br>"
                f"{x_label}: %{{customdata}}<br>"
                f"{param_labels[selected_param]}: %{{y:.3f}}<extra></extra>"
            ),
            customdata=x_tick_text,
        )
    )
    
    trend = generate_trend_analysis(profile_df, selected_param)
    
    if trend.get('has_trend'):
        trend_line_x = list(range(len(y_values)))
        trend_line_y = [trend['slope'] * x + trend['intercept'] for x in trend_line_x]
        
        fig.add_trace(
            go.Scatter(
                x=trend_line_x,
                y=trend_line_y,
                mode='lines',
                name=f'趋势线 ({trend["trend"]})',
                line=dict(dash='dash', color='red', width=2),
            )
        )
    
    fig.update_layout(
        title=f"{param_labels[selected_param]}随{ '深度' if sort_by == 'depth' else '时间' }变化趋势",
        xaxis_title=x_label,
        yaxis_title=param_labels[selected_param],
        height=500,
        hovermode="x unified",
        showlegend=True,
    )
    
    if sort_by == 'depth':
        fig.update_layout(yaxis_autorange='reversed' if sort_by == 'depth' else True)
    
    fig.update_xaxes(
        ticktext=x_tick_text,
        tickvals=list(range(len(x_tick_text))),
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    if trend.get('has_trend'):
        st.markdown("#### 📊 趋势分析")
        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        with col_t1:
            st.metric("趋势方向", trend['trend'])
        with col_t2:
            st.metric("数据点数", trend['data_points'])
        with col_t3:
            change_str = f"{trend['change_percent']:.1f}%" if trend.get('change_percent') is not None else "—"
            st.metric("变化幅度", change_str)
        with col_t4:
            r2_str = f"{trend['r_squared']:.3f}" if trend.get('r_squared') is not None else "—"
            st.metric("拟合优度 R²", r2_str)
    else:
        st.info(trend.get('message', '数据不足，无法分析趋势'))
    
    st.markdown("### 累计分布曲线对比（按深度/时间排序）")
    
    fig2 = go.Figure()
    
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    for i, sample in enumerate(samples_data):
        if sample['id'] in profile_df.index.values or sample['sample_no'] in profile_df['sample_no'].values:
            analysis = sample['analysis']
            if not analysis['cum_df'].empty:
                color = colors[i % len(colors)]
                cum_df = analysis['cum_df']
                label = f"{sample['sample_no']}"
                if sort_by == 'depth' and sample.get('depth'):
                    label = f"深度 {sample['depth']}m - {sample['sample_no']}"
                elif sort_by == 'time' and sample.get('sampling_time'):
                    label = f"{sample['sampling_time']} - {sample['sample_no']}"
                
                fig2.add_trace(
                    go.Scatter(
                        x=cum_df['sieve_size'],
                        y=cum_df['cumulative_percent'],
                        mode='lines+markers',
                        name=label,
                        line=dict(width=2, color=color),
                        marker=dict(size=6),
                    )
                )
    
    fig2.update_xaxes(type="log", title_text="粒径 (mm)")
    fig2.update_yaxes(title_text="小于该粒径累计 (%)", range=[0, 105])
    fig2.update_layout(
        height=500,
        legend_title="样本",
        hovermode="x unified"
    )
    
    st.plotly_chart(fig2, use_container_width=True)
    
    st.markdown("### 📥 导出")
    col1, col2 = st.columns(2)
    
    with col1:
        csv_data = display_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📄 剖面/时序数据 CSV",
            data=csv_data,
            file_name=f"{analysis_type}_分析数据.csv",
            mime='text/csv',
            use_container_width=True
        )
    
    with col2:
        try:
            profile_samples = []
            for _, row in profile_df.iterrows():
                for s in samples_data:
                    if s['sample_no'] == row['sample_no']:
                        profile_samples.append(s)
                        break
            
            pdf_data = generate_pdf_report(profile_samples, title=f"火山灰{analysis_type}分析报告")
            st.download_button(
                "📕 PDF 分析报告",
                data=pdf_data,
                file_name=f"{analysis_type}分析报告.pdf",
                mime='application/pdf',
                use_container_width=True
            )
        except ImportError:
            st.caption("请安装 reportlab")


def render_operation_logs():
    st.header("📄 操作日志")
    
    logs = get_operation_logs(limit=200)
    
    if not logs:
        st.info("暂无操作日志")
        return
    
    log_df = pd.DataFrame(logs)
    
    display_df = log_df[['created_at', 'operation_type', 'entity_type', 'entity_name', 'details', 'operator']].copy()
    display_df.columns = ['时间', '操作类型', '对象类型', '对象名称', '详情', '操作人']
    
    type_map = {
        'create': '创建',
        'update': '更新',
        'delete': '删除',
        'batch_delete': '批量删除',
        'update_sieve': '更新筛分数据',
        'batch_import': '批量导入',
    }
    display_df['操作类型'] = display_df['操作类型'].map(lambda x: type_map.get(x, x))
    
    entity_map = {
        'sample': '样本',
    }
    display_df['对象类型'] = display_df['对象类型'].map(lambda x: entity_map.get(x, x) if x else '')
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.caption(f"共 {len(logs)} 条操作记录（显示最近 200 条）")


def main():
    render_sidebar()
    
    page = st.session_state.current_page
    
    if page == "样本列表":
        render_sample_list()
    elif page == "新建样本":
        render_new_sample()
    elif page == "查看样本":
        render_view_sample()
    elif page == "样本对比":
        render_comparison()
    elif page == "批量导入":
        render_batch_import()
    elif page == "剖面分析":
        render_profile_analysis()
    elif page == "操作日志":
        render_operation_logs()
    else:
        render_sample_list()


if __name__ == "__main__":
    main()
