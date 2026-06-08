import streamlit as st

from db import init_db
from workflow_db import init_workflow_db
from qc_db import init_qc_db

from core import render_sidebar, navigate_to, get_current_page

from pages.samples import (
    render_sample_list,
    render_new_sample,
    render_view_sample,
    render_comparison,
    render_batch_import,
    render_profile_analysis,
    render_operation_logs,
)
from pages.workflow import render_workflow_main, render_create_task_from_sample
from pages.qc import (
    render_qc_dashboard,
    render_batch_management,
    render_instrument_management,
    render_parallel_qc,
    render_qc_alerts,
    render_retest_requests,
    render_qc_report,
)

st.set_page_config(
    page_title="火山灰样本分析系统",
    page_icon="🌋",
    layout="wide",
)

init_db()
init_workflow_db()
init_qc_db()

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


SAMPLE_PAGES = [
    "样本列表", "新建样本", "查看样本", "样本对比",
    "批量导入", "剖面分析", "操作日志",
]

WORKFLOW_PAGES = ["流程任务", "协作看板", "流程统计", "超期提醒"]

QC_PAGES = [
    "质量看板", "实验批次", "仪器管理", "平行样对比",
    "质量预警", "复测申请", "质量报告",
]


def _is_sample_page(page: str) -> bool:
    return page in SAMPLE_PAGES


def _is_workflow_page(page: str) -> bool:
    return page in WORKFLOW_PAGES


def _is_qc_page(page: str) -> bool:
    return page in QC_PAGES


def _render_sample_page(page: str) -> None:
    page_renderers = {
        "样本列表": render_sample_list,
        "新建样本": render_new_sample,
        "查看样本": render_view_sample,
        "样本对比": render_comparison,
        "批量导入": render_batch_import,
        "剖面分析": render_profile_analysis,
        "操作日志": render_operation_logs,
    }
    renderer = page_renderers.get(page, render_sample_list)
    renderer()


def _render_workflow_page(page: str) -> None:
    if page == "创建任务":
        render_sidebar()
        st.header("📝 创建流程任务")
        render_create_task_from_sample()
    else:
        if "wf_page" not in st.session_state:
            st.session_state.wf_page = "任务列表"
        page_map = {
            "流程任务": "任务列表",
            "协作看板": "协作看板",
            "流程统计": "流程统计",
            "超期提醒": "超期提醒",
        }
        st.session_state.wf_page = page_map.get(page, "任务列表")
        render_workflow_main()


def _render_qc_page(page: str) -> None:
    render_sidebar()
    page_renderers = {
        "质量看板": render_qc_dashboard,
        "实验批次": render_batch_management,
        "仪器管理": render_instrument_management,
        "平行样对比": render_parallel_qc,
        "质量预警": render_qc_alerts,
        "复测申请": render_retest_requests,
        "质量报告": render_qc_report,
    }
    renderer = page_renderers.get(page, render_qc_dashboard)
    renderer()


def main():
    page = get_current_page()
    
    if _is_sample_page(page):
        render_sidebar()
        _render_sample_page(page)
    elif _is_workflow_page(page) or page == "创建任务":
        _render_workflow_page(page)
    elif _is_qc_page(page):
        _render_qc_page(page)
    else:
        render_sidebar()
        render_sample_list()


if __name__ == "__main__":
    main()
