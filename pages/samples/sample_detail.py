import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core import navigate_to
from db import (
    get_sample,
    get_default_sieve_sizes,
    get_all_groups,
    update_sample,
    batch_add_sieve_data,
)
from analysis import (
    calculate_analysis,
    validate_sieve_data,
    get_sieve_label,
    generate_export_data,
    generate_summary_export,
    suggest_missing_sieve_fill,
    get_reliability_color,
)
from report import generate_pdf_report, generate_word_report
from workflow_db import (
    get_task_by_sample,
    create_task_for_sample,
    get_stage_name,
    get_status_name,
    get_priority_name,
)


def _render_workflow_status(sample_id):
    task = get_task_by_sample(sample_id)
    if task:
        st.info(
            f"🔄 **流程状态：** {get_stage_name(task['current_stage'])} - "
            f"{get_status_name(task['task_status'])} "
            f"（优先级：{get_priority_name(task.get('priority', 'normal'))}）"
        )
        col_task1, col_task2 = st.columns([1, 4])
        with col_task1:
            if st.button("📋 查看任务详情", use_container_width=True, type="primary"):
                st.session_state.wf_viewing_task_id = task['id']
                st.session_state.wf_page = "任务列表"
                navigate_to("流程任务")
        with col_task2:
            st.caption(
                f"负责人: {task.get('assigned_to') or '未分派'} | "
                f"截止时间: {task.get('deadline') or '未设置'} | "
                f"创建时间: {task.get('created_at', '')}"
            )
        st.markdown("---")
    else:
        with st.expander("➕ 创建流程任务", expanded=False):
            st.markdown("为该样本创建审批流程任务，跟踪样本在各阶段的处理进度。")
            priority_options = {'高': 'high', '普通': 'normal', '低': 'low'}
            priority_label = st.selectbox("任务优先级", list(priority_options.keys()), index=1,
                                          key="view_sample_task_priority")
            deadline_hours = st.number_input(
                "第一阶段截止时间（小时后）",
                min_value=1, max_value=720, value=24, step=1,
                key="view_sample_task_deadline"
            )
            task_description = st.text_area("任务描述", height=60, key="view_sample_task_desc")
            if st.button("创建任务", type="primary", use_container_width=True):
                task_id = create_task_for_sample(
                    sample_id=sample_id,
                    sample_no=get_sample(sample_id)['sample_no'],
                    created_by='system',
                    description=task_description,
                    priority=priority_options[priority_label],
                    deadline_hours=deadline_hours,
                )
                st.success(f"任务创建成功！任务ID: {task_id}")
                st.rerun()
        st.markdown("---")


def _render_basic_info(sample):
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


def _render_edit_basic_form(sample):
    all_groups = get_all_groups()
    with st.expander("✏️ 编辑基础信息", expanded=False):
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


def _render_analysis_results(analysis, sample):
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
            st.markdown("**分析可信度**")
            st.markdown(
                f"<h2 style='color: {reliab_color}; margin: 0;'>"
                f"{analysis['reliability_score']:.0f}/100</h2>",
                unsafe_allow_html=True
            )
            st.markdown(
                f"<p style='color: {reliab_color}; font-weight: bold; margin-top: 4px;'>"
                f"● {analysis['reliability_level']}</p>",
                unsafe_allow_html=True
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


def _render_missing_sieve_suggestions(default_sieves, existing_sieves, sample):
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


def _render_sieve_data_detail(analysis):
    with st.expander("📋 筛分数据明细", expanded=True):
        df_display = analysis['df'].copy()
        if not df_display.empty:
            df_display['粒级'] = df_display['sieve_size'].apply(get_sieve_label)
            df_display = df_display[['粒级', 'sieve_size', 'retained_weight', 'weight_percent']]
            df_display.columns = ['粒级', '筛孔(mm)', '留存重量(g)', '占比(%)']
            
            cum_df_display = analysis['cum_df'].copy()
            max_size = df_display['筛孔(mm)'].max()
            cum_df_display = cum_df_display[cum_df_display['sieve_size'] <= max_size]
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


def _render_size_distribution_chart(analysis):
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


def _render_edit_sieve_form(sample, default_sieves, existing_sieves):
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
            
            batch_add_sieve_data(sample['id'], sieve_data_list)
            st.success("筛分数据已更新！")
            st.rerun()


def _render_export_section(sample, analysis):
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

    _render_workflow_status(sample_id)
    _render_basic_info(sample)
    _render_edit_basic_form(sample)
    _render_analysis_results(analysis, sample)
    _render_missing_sieve_suggestions(default_sieves, existing_sieves, sample)
    _render_sieve_data_detail(analysis)
    _render_size_distribution_chart(analysis)
    _render_edit_sieve_form(sample, default_sieves, existing_sieves)
    _render_export_section(sample, analysis)
