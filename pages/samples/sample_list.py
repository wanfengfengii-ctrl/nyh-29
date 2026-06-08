import streamlit as st
import pandas as pd
from datetime import datetime

from core import (
    navigate_to,
    render_page_header,
    render_data_table,
    render_filter_bar,
    render_empty_state,
    render_action_bar,
    StatusColor,
    PriorityColor,
)
from db import (
    get_all_samples,
    get_sample,
    delete_sample,
    batch_delete_samples,
    get_all_groups,
)
from workflow_db import (
    get_task_by_sample,
    create_task_for_sample,
    get_stage_name,
    get_status_name,
    get_priority_name,
)


def _is_task_overdue(task):
    if not task or not task.get('deadline'):
        return False
    if task['task_status'] not in ('pending', 'in_progress'):
        return False
    try:
        deadline_dt = datetime.strptime(task['deadline'], '%Y-%m-%d %H:%M:%S')
        return deadline_dt < datetime.now()
    except (ValueError, TypeError):
        return False


def _prepare_display_data(samples, sample_task_map):
    display_data = []
    for s in samples:
        task = sample_task_map.get(s['id'])
        if task:
            task_stage = get_stage_name(task['current_stage'])
            task_status = get_status_name(task['task_status'])
            task_status_code = task['task_status']
            is_overdue = _is_task_overdue(task)
            if is_overdue:
                task_status = '已超期'
                task_status_code = 'overdue'
            task_priority = get_priority_name(task.get('priority', 'normal'))
            task_priority_code = task.get('priority', 'normal')
        else:
            task_stage = '未创建'
            task_status = '—'
            task_status_code = 'none'
            task_priority = '—'
            task_priority_code = 'none'
            is_overdue = False

        display_data.append({
            '样本编号': s['sample_no'],
            '采样点': s['sampling_site'],
            '喷发层位': s.get('eruption_layer', ''),
            '分组': s.get('group_name', ''),
            '总重量(g)': s['total_weight'],
            '粒级数': s['sieve_count'],
            '流程阶段': task_stage,
            '任务状态': task_status,
            '_status_code': task_status_code,
            '优先级': task_priority,
            '_priority_code': task_priority_code,
            '_is_overdue': is_overdue,
            '创建时间': s['created_at'],
            'id': s['id'],
        })
    return display_data


def _get_status_color_map():
    return {
        'pending': 'orange',
        'in_progress': '#1890ff',
        'completed': 'green',
        'returned': 'red',
        'overdue': 'red',
        'none': 'gray',
        '—': 'gray',
    }


def _get_priority_color_map():
    return {
        'high': 'red',
        'normal': 'orange',
        'low': 'green',
        'none': 'gray',
        '—': 'gray',
    }


def _style_dataframe(df):
    status_color_map = _get_status_color_map()
    priority_color_map = _get_priority_color_map()

    def _style_row(row):
        styles = []
        is_overdue = row.get('_is_overdue', False)
        status_code = row.get('_status_code', '')
        priority_code = row.get('_priority_code', '')
        for col in row.index:
            style = ''
            if is_overdue:
                style += 'background-color: #fff1f0; '
            if col == '任务状态':
                color = status_color_map.get(status_code, 'gray')
                style += f'color: {color}; font-weight: bold; '
            if col == '优先级':
                pri_color = priority_color_map.get(priority_code, 'gray')
                style += f'color: {pri_color}; font-weight: bold; '
            styles.append(style)
        return styles

    styled_df = df.style.apply(_style_row, axis=1)
    styled_df = styled_df.hide(axis="columns", subset=['_status_code', '_priority_code', '_is_overdue', 'id'])
    return styled_df


def render_sample_list():
    render_page_header("📋 火山灰样本列表")
    
    samples = get_all_samples()
    
    if not samples:
        render_empty_state("暂无样本数据，点击左侧「新建样本」开始录入。")
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
    
    sample_task_map = {}
    for s in samples:
        task = get_task_by_sample(s['id'])
        if task:
            sample_task_map[s['id']] = task

    display_data = _prepare_display_data(samples, sample_task_map)
    df = pd.DataFrame(display_data)
    styled_df = _style_dataframe(df)

    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    st.markdown("### 操作")

    sample_options = {f"{s['sample_no']} - {s['sampling_site']}": s['id'] for s in samples}
    selected_label = st.selectbox("选择样本", list(sample_options.keys()), label_visibility="collapsed")
    selected_id = sample_options[selected_label]

    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])

    with col1:
        st.write("")

    with col2:
        if st.button("查看详情", use_container_width=True):
            navigate_to("查看样本", viewing_sample_id=selected_id)

    with col3:
        if st.button("✏️ 编辑", use_container_width=True):
            navigate_to("查看样本", viewing_sample_id=selected_id)

    with col4:
        has_task = selected_id in sample_task_map
        if has_task:
            if st.button("🔄 查看任务", use_container_width=True, type="primary"):
                task = sample_task_map[selected_id]
                st.session_state.wf_viewing_task_id = task['id']
                st.session_state.wf_page = "任务列表"
                navigate_to("流程任务")
        else:
            if st.button("➕ 创建任务", use_container_width=True):
                task_id = create_task_for_sample(
                    sample_id=selected_id,
                    sample_no=selected_label.split(' - ')[0],
                    created_by='system',
                    description='从样本列表创建',
                    priority='normal',
                    deadline_hours=24,
                )
                st.success(f"任务创建成功！ID: {task_id}")
                st.rerun()

    with col5:
        if st.session_state.get('confirm_delete_id') == selected_id:
            st.warning("⚠️ 确认删除？此操作不可恢复！")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("确认删除", type="primary", use_container_width=True, key="confirm_del_yes"):
                    delete_sample(selected_id)
                    st.success("样本已删除")
                    st.session_state.confirm_delete_id = None
                    st.rerun()
            with col_no:
                if st.button("取消", use_container_width=True, key="confirm_del_no"):
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
        
        if st.session_state.get('batch_delete_ids') == batch_ids:
            st.error(f"⚠️ 确认删除 {len(batch_ids)} 个样本？此操作不可恢复！")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("确认批量删除", type="primary", use_container_width=True, key="batch_del_yes"):
                    count = batch_delete_samples(batch_ids)
                    st.success(f"已成功删除 {count} 个样本")
                    st.session_state.batch_delete_ids = []
                    st.rerun()
            with col_no:
                if st.button("取消", use_container_width=True, key="batch_del_no"):
                    st.session_state.batch_delete_ids = []
                    st.rerun()
        else:
            if st.button("批量删除选中样本", type="secondary"):
                st.session_state.batch_delete_ids = batch_ids
                st.rerun()
