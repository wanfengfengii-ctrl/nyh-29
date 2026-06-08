import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core import render_page_header, render_empty_state
from db import get_all_samples, get_sample, get_all_groups
from analysis import (
    calculate_analysis,
    prepare_profile_analysis,
    generate_trend_analysis,
    get_sieve_label,
)
from report import generate_pdf_report


def render_profile_analysis():
    render_page_header("📈 时间序列/剖面对比分析")
    
    samples = get_all_samples()
    
    if len(samples) < 2:
        render_empty_state("至少需要 2 个样本才能进行剖面/时间序列分析。")
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
        full_sample = get_sample(sample['id'])
        if full_sample:
            analysis = calculate_analysis(full_sample['sieve_data'], full_sample['total_weight'])
            samples_data.append({**full_sample, 'analysis': analysis})
    
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
