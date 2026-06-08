import streamlit as st
import pandas as pd

from core import navigate_to, render_page_header
from db import batch_import_samples
from report import get_import_template_csv, parse_import_csv


def render_batch_import():
    render_page_header("📥 批量导入样本")
    
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
