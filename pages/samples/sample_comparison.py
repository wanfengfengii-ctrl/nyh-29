import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core import render_page_header, render_empty_state
from db import get_all_samples, get_sample, get_all_groups, get_samples_by_group, get_default_sieve_sizes
from analysis import (
    calculate_analysis,
    get_sieve_label,
    generate_export_data,
    generate_summary_export,
)
from report import generate_pdf_report, generate_word_report


def render_comparison():
    render_page_header("📊 多样本对比分析")
    
    samples = get_all_samples()
    
    if len(samples) < 2:
        render_empty_state("至少需要 2 个样本才能进行对比，请先创建更多样本。")
        return
    
    sample_options = {f"{s['sample_no']} - {s['sampling_site']}": s['id'] for s in samples}
    sample_labels = list(sample_options.keys())
    
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
            default_selected = sample_labels[:3] if len(sample_labels) >= 3 else sample_labels
    else:
        default_selected = sample_labels[:3] if len(sample_labels) >= 3 else sample_labels
    
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
