import streamlit as st

from workflow_pages import (
    init_session_state,
    render_workflow_main as _render_workflow_main,
    render_create_task_from_sample as _render_create_task_from_sample,
)


def render_workflow_main():
    init_session_state()
    
    page = st.session_state.get("wf_page", "任务列表")
    page_map = {
        "流程任务": "任务列表",
        "协作看板": "协作看板",
        "流程统计": "流程统计",
        "超期提醒": "超期提醒",
    }
    
    main_page = st.session_state.get("current_page", "流程任务")
    if main_page in page_map:
        st.session_state.wf_page = page_map[main_page]
    
    _render_workflow_main()


def render_create_task_from_sample():
    _render_create_task_from_sample()
