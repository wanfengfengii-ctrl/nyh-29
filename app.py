import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

from db import (
    init_db,
    get_all_samples,
    get_sample,
    get_sample_by_no,
    add_sample,
    update_sample,
    delete_sample,
    batch_add_sieve_data,
    get_default_sieve_sizes,
)
from analysis import (
    calculate_analysis,
    validate_sieve_data,
    get_sieve_label,
    generate_export_data,
    generate_summary_export,
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


def navigate_to(page, **kwargs):
    st.session_state.current_page = page
    for key, value in kwargs.items():
        st.session_state[key] = value
    st.rerun()


def render_sidebar():
    with st.sidebar:
        st.title("🌋 火山灰分析系统")
        st.markdown("---")
        
        if st.button("📋 样本列表", use_container_width=True, type="primary" if st.session_state.current_page == "样本列表" else "secondary"):
            navigate_to("样本列表")
        
        if st.button("➕ 新建样本", use_container_width=True, type="primary" if st.session_state.current_page == "新建样本" else "secondary"):
            navigate_to("新建样本")
        
        if st.button("📊 样本对比", use_container_width=True, type="primary" if st.session_state.current_page == "样本对比" else "secondary"):
            navigate_to("样本对比")
        
        st.markdown("---")
        st.caption("地质实验室 · 火山灰筛分分析")


def render_sample_list():
    st.header("📋 火山灰样本列表")
    
    samples = get_all_samples()
    
    if not samples:
        st.info("暂无样本数据，点击左侧「新建样本」开始录入。")
        return
    
    df = pd.DataFrame(samples)
    display_df = df[['sample_no', 'sampling_site', 'eruption_layer', 'total_weight', 'sieve_count', 'created_at']].copy()
    display_df.columns = ['样本编号', '采样点', '喷发层位', '总重量(g)', '粒级数', '创建时间']
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.markdown("### 操作")
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        sample_options = {f"{s['sample_no']} - {s['sampling_site']}": s['id'] for s in samples}
        selected = st.selectbox("选择样本", list(sample_options.keys()), label_visibility="collapsed")
        selected_id = sample_options[selected]
    
    with col2:
        if st.button("查看详情", use_container_width=True):
            navigate_to("查看样本", viewing_sample_id=selected_id)
    
    with col3:
        if st.button("删除样本", use_container_width=True, type="secondary"):
            sample = get_sample(selected_id)
            if sample:
                delete_sample(selected_id)
                st.success(f"样本 {sample['sample_no']} 已删除")
                st.rerun()


def render_new_sample():
    st.header("➕ 新建火山灰样本")
    
    default_sieves = get_default_sieve_sizes()
    
    with st.form("new_sample_form"):
        st.subheader("基本信息")
        col1, col2 = st.columns(2)
        with col1:
            sample_no = st.text_input("样本编号 *", help="样本编号不能重复")
            sampling_site = st.text_input("采样点 *")
            eruption_layer = st.text_input("喷发层位")
        with col2:
            total_weight = st.number_input("样本总重量 (g) *", min_value=0.0, step=0.1, value=100.0)
            description = st.text_area("备注", height=100)
        
        st.markdown("---")
        st.subheader("筛分数据 (各粒级留存重量)")
        
        sieve_weights = {}
        for size in default_sieves:
            label = get_sieve_label(size)
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
                sample_no.strip(),
                sampling_site.strip(),
                eruption_layer.strip(),
                total_weight,
                description.strip()
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
    
    with st.expander("基本信息", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("样本编号", sample['sample_no'])
        with col2:
            st.metric("采样点", sample['sampling_site'])
        with col3:
            st.metric("喷发层位", sample['eruption_layer'] or '未记录')
        with col4:
            st.metric("总重量", f"{sample['total_weight']:.2f} g")
        
        if sample['description']:
            st.markdown(f"**备注：** {sample['description']}")
    
    with st.expander("✏️ 编辑基础信息", expanded=False):
        with st.form("edit_basic_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_sample_no = st.text_input("样本编号 *", value=sample['sample_no'])
                new_sampling_site = st.text_input("采样点 *", value=sample['sampling_site'])
                new_eruption_layer = st.text_input("喷发层位", value=sample.get('eruption_layer') or '')
            with col2:
                new_total_weight = st.number_input(
                    "样本总重量 (g) *",
                    min_value=0.0,
                    step=0.1,
                    value=float(sample['total_weight'])
                )
                new_description = st.text_area(
                    "备注",
                    value=sample.get('description') or '',
                    height=100
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
                                sample['id'],
                                new_sample_no.strip(),
                                new_sampling_site.strip(),
                                new_eruption_layer.strip(),
                                new_total_weight,
                                new_description.strip()
                            )
                            st.success("基础信息已更新！")
                            st.rerun()
    
    analysis = calculate_analysis(sample['sieve_data'], sample['total_weight'])
    
    with st.expander("筛分分析结果", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            d50_val = f"{analysis['median_diameter']:.3f} mm" if analysis['median_diameter'] else "—"
            st.metric("中值粒径 (D50)", d50_val)
        with col2:
            sc_val = f"{analysis['sorting_coefficient']:.2f}" if analysis['sorting_coefficient'] else "—"
            st.metric("分选系数", sc_val)
        with col3:
            grade = analysis['sorting_grade']
            grade_color = {"分选良好": "green", "分选一般": "orange", "分选差": "red"}.get(grade, "gray")
            st.metric("沉积分选评价", grade)
        with col4:
            retained_pct = analysis['total_retained'] / sample['total_weight'] * 100 if sample['total_weight'] > 0 else 0
            st.metric("筛分回收率", f"{retained_pct:.1f}%")
        
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
    
    with st.expander("筛分数据明细", expanded=True):
        df_display = analysis['df'].copy()
        if not df_display.empty:
            df_display['粒级'] = df_display['sieve_size'].apply(get_sieve_label)
            df_display = df_display[['粒级', 'sieve_size', 'retained_weight', 'weight_percent']]
            df_display.columns = ['粒级', '筛孔(mm)', '留存重量(g)', '占比(%)']
            
            cum_df_display = analysis['cum_df'].copy()
            cum_df_display = cum_df_display[cum_df_display['sieve_size'] <= df_display['sieve_size'].max()]
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
    
    with st.expander("粒径分布图", expanded=True):
        if analysis['df'].empty:
            st.info("暂无筛分数据，无法生成图表")
        else:
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing= 0.08,
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
            
            missing_sieves = [s for s in default_sieves if s not in existing_sieves]
            if missing_sieves:
                missing_labels = [get_sieve_label(s) for s in sorted(missing_sieves)]
                st.warning(f"⚠️ 缺失粒级数据：{', '.join(missing_labels)}")
    
    st.markdown("---")
    st.subheader("编辑筛分数据")
    st.caption("修改后点击「保存更新」，所有统计结果将自动重新计算")
    
    with st.form("edit_sieve_form"):
        sieve_weights = {}
        for size in default_sieves:
            label = get_sieve_label(size)
            current_val = existing_sieves.get(size, 0.0)
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
    
    col_export1, col_export2 = st.columns(2)
    with col_export1:
        if not analysis['df'].empty:
            export_df = generate_export_data([{
                **sample,
                'analysis': analysis
            }])
            csv = export_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📥 导出详细 CSV",
                data=csv,
                file_name=f"样本_{sample['sample_no']}_筛分明细.csv",
                mime='text/csv',
                use_container_width=True
            )
    with col_export2:
        if not analysis['df'].empty:
            summary_df = generate_summary_export([{
                **sample,
                'analysis': analysis
            }])
            csv = summary_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📥 导出汇总 CSV",
                data=csv,
                file_name=f"样本_{sample['sample_no']}_分析汇总.csv",
                mime='text/csv',
                use_container_width=True
            )


def render_comparison():
    st.header("📊 多样本对比分析")
    
    samples = get_all_samples()
    
    if len(samples) < 2:
        st.info("至少需要 2 个样本才能进行对比，请先创建更多样本。")
        return
    
    sample_options = {f"{s['sample_no']} - {s['sampling_site']}": s['id'] for s in samples}
    selected_labels = st.multiselect(
        "选择要对比的样本（至少2个）",
        list(sample_options.keys()),
        default=list(sample_options.keys())[:3] if len(sample_options) >= 3 else list(sample_options.keys())
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
    
    st.markdown("### 导出对比数据")
    col1, col2 = st.columns(2)
    
    with col1:
        export_detail = generate_export_data(samples_data)
        csv_detail = export_detail.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 导出所有详细数据 CSV",
            data=csv_detail,
            file_name="多样本筛分对比_明细.csv",
            mime='text/csv',
            use_container_width=True
        )
    
    with col2:
        summary_export = generate_summary_export(samples_data)
        csv_summary = summary_export.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 导出汇总对比 CSV",
            data=csv_summary,
            file_name="多样本筛分对比_汇总.csv",
            mime='text/csv',
            use_container_width=True
        )


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
    else:
        render_sample_list()


if __name__ == "__main__":
    main()
