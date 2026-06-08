import streamlit as st
from typing import List, Tuple, Optional

from .router import navigate_to


class NavGroup:
    def __init__(self, title: str, items: List[Tuple[str, str]], icon: str = ""):
        self.title = title
        self.items = items
        self.icon = icon


def _render_nav_button(label: str, page: str, is_active: bool) -> None:
    if st.button(label, use_container_width=True, type="primary" if is_active else "secondary"):
        navigate_to(page)


def _render_nav_group(group: NavGroup, current_page: str) -> None:
    if group.title:
        st.subheader(f"{group.icon} {group.title}" if group.icon else group.title)
    
    for label, page in group.items:
        is_active = current_page == page
        _render_nav_button(label, page, is_active)


def render_sidebar() -> None:
    current_page = st.session_state.get("current_page", "样本列表")
    
    with st.sidebar:
        st.title("🌋 火山灰分析系统")
        st.markdown("---")

        sample_group = NavGroup(
            title="",
            items=[
                ("📋 样本列表", "样本列表"),
                ("➕ 新建样本", "新建样本"),
                ("📥 批量导入", "批量导入"),
                ("📊 样本对比", "样本对比"),
                ("📈 剖面分析", "剖面分析"),
            ]
        )
        _render_nav_group(sample_group, current_page)

        st.markdown("---")

        workflow_group = NavGroup(
            title="流程审批",
            icon="🔄",
            items=[
                ("📋 任务列表", "流程任务"),
                ("🎯 协作看板", "协作看板"),
                ("📊 流程统计", "流程统计"),
                ("⏰ 超期提醒", "超期提醒"),
                ("📝 创建任务", "创建任务"),
            ]
        )
        _render_nav_group(workflow_group, current_page)

        st.markdown("---")

        qc_group = NavGroup(
            title="质量控制",
            icon="📊",
            items=[
                ("📈 质量看板", "质量看板"),
                ("📦 实验批次", "实验批次"),
                ("🔬 仪器管理", "仪器管理"),
                ("⚖️ 平行样对比", "平行样对比"),
                ("🔔 质量预警", "质量预警"),
                ("🔄 复测申请", "复测申请"),
                ("📄 质量报告", "质量报告"),
            ]
        )
        _render_nav_group(qc_group, current_page)

        st.markdown("---")

        other_group = NavGroup(
            title="",
            items=[
                ("📄 操作日志", "操作日志"),
            ]
        )
        _render_nav_group(other_group, current_page)

        st.markdown("---")
        st.caption("地质实验室 · 火山灰筛分分析")
