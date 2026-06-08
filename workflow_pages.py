import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import csv

from workflow_db import (
    init_workflow_db,
    get_all_users,
    get_user,
    get_stages,
    get_stage_by_code,
    create_task_for_sample,
    get_task,
    get_task_by_sample,
    get_all_tasks,
    assign_task,
    start_task,
    complete_stage,
    return_task,
    add_approval,
    get_task_stage_logs,
    get_approvals,
    get_overdue_tasks,
    get_user_tasks,
    get_workflow_statistics,
    update_task_deadline,
    get_stage_name,
    get_status_name,
    get_priority_name,
    WORKFLOW_STAGES,
    TASK_STATUS,
)
from db import get_all_samples, get_sample, get_all_groups


def init_session_state():
    if "wf_current_user" not in st.session_state:
        st.session_state.wf_current_user = "admin"
    if "wf_page" not in st.session_state:
        st.session_state.wf_page = "任务列表"
    if "wf_viewing_task_id" not in st.session_state:
        st.session_state.wf_viewing_task_id = None
    if "wf_filters" not in st.session_state:
        st.session_state.wf_filters = {}


def render_workflow_sidebar():
    with st.sidebar:
        st.title("🔄 流程审批与协作")
        st.markdown("---")

        users = get_all_users()
        user_options = {f"{u['full_name']} ({u['username']})": u['username'] for u in users}
        current_display = next(
            (k for k, v in user_options.items() if v == st.session_state.wf_current_user),
            list(user_options.keys())[0] if user_options else "系统管理员"
        )

        st.markdown("👤 当前操作人")
        selected_user = st.selectbox(
            "选择操作人",
            list(user_options.keys()),
            index=list(user_options.keys()).index(current_display) if current_display in user_options else 0,
            label_visibility="collapsed"
        )
        st.session_state.wf_current_user = user_options[selected_user]

        st.markdown("---")

        nav_items = [
            ("📋 任务列表", "任务列表"),
            ("🎯 协作看板", "协作看板"),
            ("📊 流程统计", "流程统计"),
            ("📝 超期提醒", "超期提醒"),
        ]

        for label, page in nav_items:
            is_active = st.session_state.wf_page == page
            if st.button(label, use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state.wf_page = page
                st.session_state.wf_viewing_task_id = None
                st.rerun()

        st.markdown("---")

        stats = get_workflow_statistics()
        st.caption("📊 快速统计")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("待处理", stats.get('by_status', {}).get('pending', 0))
        with col2:
            st.metric("处理中", stats.get('by_status', {}).get('in_progress', 0))

        col3, col4 = st.columns(2)
        with col3:
            st.metric("已完成", stats.get('by_status', {}).get('completed', 0))
        with col4:
            st.metric("已超期", stats.get('overdue_count', 0))

        st.markdown("---")
        st.caption("地质实验室 · 流程管理")


def get_status_color(status):
    colors = {
        'pending': 'orange',
        'in_progress': 'blue',
        'completed': 'green',
        'returned': 'red',
        'overdue': 'red',
    }
    return colors.get(status, 'gray')


def get_priority_color(priority):
    colors = {
        'high': 'red',
        'normal': 'orange',
        'low': 'green',
    }
    return colors.get(priority, 'gray')


def render_task_list():
    st.header("📋 任务列表")

    col_filters = st.columns([2, 1, 1, 1, 1])

    with col_filters[0]:
        search_sample = st.text_input("搜索样本编号/采样点", "")

    stages = get_stages()
    stage_options = {"全部阶段": None}
    for s in stages:
        stage_options[s['stage_name']] = s['stage_code']

    with col_filters[1]:
        stage_select = st.selectbox("阶段筛选", list(stage_options.keys()))
        selected_stage = stage_options[stage_select]

    status_options = {
        "全部状态": None,
        "待处理": "pending",
        "处理中": "in_progress",
        "已完成": "completed",
        "已退回": "returned",
    }
    with col_filters[2]:
        status_select = st.selectbox("状态筛选", list(status_options.keys()))
        selected_status = status_options[status_select]

    users = get_all_users()
    user_options = {"全部人员": None}
    for u in users:
        user_options[f"{u['full_name']}"] = u['username']
    with col_filters[3]:
        assignee_select = st.selectbox("负责人", list(user_options.keys()))
        selected_assignee = user_options[assignee_select]

    priority_options = {
        "全部优先级": None,
        "高": "high",
        "普通": "normal",
        "低": "low",
    }
    with col_filters[4]:
        priority_select = st.selectbox("优先级", list(priority_options.keys()))
        selected_priority = priority_options[priority_select]

    col_filters2 = st.columns([1, 1, 1, 1])

    all_groups = get_all_groups()
    group_options = {"全部分组": None}
    for g in all_groups:
        group_options[g] = g
    with col_filters2[0]:
        group_select = st.selectbox("分组筛选", list(group_options.keys()))
        selected_group = group_options[group_select]

    with col_filters2[1]:
        eruption_search = st.text_input("喷发层位", "")

    with col_filters2[2]:
        date_from = st.date_input("创建日期从", value=None)

    with col_filters2[3]:
        date_to = st.date_input("创建日期至", value=None)

    tasks = get_all_tasks(
        status=selected_status,
        stage=selected_stage,
        assignee=selected_assignee,
        priority=selected_priority,
        sample_no=search_sample if search_sample else None,
        group_name=selected_group,
        eruption_layer=eruption_search if eruption_search else None,
        date_from=date_from.strftime('%Y-%m-%d') if date_from else None,
        date_to=date_to.strftime('%Y-%m-%d 23:59:59') if date_to else None,
    )

    if not tasks:
        st.info("暂无任务数据。可在样本列表中为样本创建任务。")
        return

    st.markdown(f"**共 {len(tasks)} 条任务**")

    display_data = []
    for t in tasks:
        is_overdue = False
        if t.get('deadline') and t['task_status'] in ('pending', 'in_progress'):
            try:
                deadline_dt = datetime.strptime(t['deadline'], '%Y-%m-%d %H:%M:%S')
                is_overdue = deadline_dt < datetime.now()
            except (ValueError, TypeError):
                pass

        display_data.append({
            '任务ID': t['id'],
            '样本编号': t['sample_no'],
            '采样点': t.get('sampling_site', ''),
            '喷发层位': t.get('eruption_layer', ''),
            '分组': t.get('group_name', ''),
            '当前阶段': get_stage_name(t['current_stage']),
            '状态': get_status_name(t['task_status']) if not is_overdue else '已超期',
            '状态码': t['task_status'] if not is_overdue else 'overdue',
            '优先级': get_priority_name(t.get('priority', 'normal')),
            '优先级码': t.get('priority', 'normal'),
            '负责人': t.get('assigned_to', '未分派') if t.get('assigned_to') else '未分派',
            '截止时间': t.get('deadline', ''),
            '创建时间': t.get('created_at', ''),
            'is_overdue': is_overdue,
        })

    df = pd.DataFrame(display_data)

    def highlight_status(row):
        status = row['状态码']
        color = get_status_color(status)
        return [f'color: {color}; font-weight: bold' if col == '状态' else '' for col in row.index]

    st.dataframe(
        df.drop(columns=['状态码', '优先级码', 'is_overdue']),
        use_container_width=True,
        hide_index=True,
        height=400,
    )

    st.markdown("---")
    st.subheader("任务操作")

    task_options = {f"{t['sample_no']} - {get_stage_name(t['current_stage'])} - {get_status_name(t['task_status'])}": t['id']
                    for t in tasks}

    col_op1, col_op2, col_op3 = st.columns([3, 1, 1])
    with col_op1:
        selected_task_label = st.selectbox("选择任务", list(task_options.keys()),
                                           label_visibility="collapsed")
        selected_task_id = task_options[selected_task_label]

    with col_op2:
        if st.button("📋 查看详情", use_container_width=True, type="primary"):
            st.session_state.wf_viewing_task_id = selected_task_id
            st.rerun()

    with col_op3:
        if st.button("🚀 快速处理", use_container_width=True):
            task = get_task(selected_task_id)
            if task and task['task_status'] == 'pending' and task.get('assigned_to') == st.session_state.wf_current_user:
                start_task(selected_task_id, st.session_state.wf_current_user, "快速开始处理")
                st.success("已开始处理！")
                st.rerun()
            elif task and task['task_status'] == 'in_progress':
                complete_stage(selected_task_id, st.session_state.wf_current_user, "快速完成")
                st.success("已完成当前阶段！")
                st.rerun()
            else:
                st.warning("该任务当前状态无法快速处理")

    st.markdown("---")
    st.subheader("📥 导出任务数据")

    col_export1, col_export2 = st.columns([1, 3])
    with col_export1:
        if st.button("📄 导出 CSV", use_container_width=True):
            export_df = pd.DataFrame(display_data)
            export_df = export_df.drop(columns=['状态码', '优先级码', 'is_overdue'])
            csv_data = export_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "⬇️ 下载任务列表 CSV",
                data=csv_data,
                file_name=f"流程任务列表_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime='text/csv',
                use_container_width=True,
            )


def render_task_detail():
    task_id = st.session_state.wf_viewing_task_id
    task = get_task(task_id)

    if not task:
        st.error("任务不存在")
        return

    col1, col2 = st.columns([4, 1])
    with col1:
        st.header(f"📋 任务详情 - {task['sample_no']}")
    with col2:
        if st.button("← 返回列表", use_container_width=True):
            st.session_state.wf_viewing_task_id = None
            st.rerun()

    sample = get_sample(task['sample_id'])

    is_overdue = False
    if task.get('deadline') and task['task_status'] in ('pending', 'in_progress'):
        try:
            deadline_dt = datetime.strptime(task['deadline'], '%Y-%m-%d %H:%M:%S')
            is_overdue = deadline_dt < datetime.now()
        except (ValueError, TypeError):
            pass

    st.markdown("### 📝 任务基本信息")

    info_cols = st.columns(4)
    with info_cols[0]:
        st.metric("任务ID", task['id'])
    with info_cols[1]:
        status_display = get_status_name(task['task_status']) if not is_overdue else '已超期'
        st.metric("任务状态", status_display)
    with info_cols[2]:
        st.metric("当前阶段", get_stage_name(task['current_stage']))
    with info_cols[3]:
        st.metric("优先级", get_priority_name(task.get('priority', 'normal')))

    info_cols2 = st.columns(4)
    with info_cols2[0]:
        assignee_name = '未分派'
        if task.get('assigned_to'):
            user = get_user(task['assigned_to'])
            assignee_name = user['full_name'] if user else task['assigned_to']
        st.metric("负责人", assignee_name)
    with info_cols2[1]:
        st.metric("创建人", task.get('created_by', 'system'))
    with info_cols2[2]:
        st.metric("创建时间", task.get('created_at', '')[:19] if task.get('created_at') else '')
    with info_cols2[3]:
        deadline_display = task.get('deadline', '未设置')
        if deadline_display and len(deadline_display) > 19:
            deadline_display = deadline_display[:19]
        st.metric("截止时间", deadline_display)

    if sample:
        with st.expander("🔬 样本详情", expanded=False):
            sample_info_cols = st.columns(4)
            with sample_info_cols[0]:
                st.metric("样本编号", sample['sample_no'])
            with sample_info_cols[1]:
                st.metric("采样点", sample['sampling_site'])
            with sample_info_cols[2]:
                st.metric("喷发层位", sample.get('eruption_layer') or '未记录')
            with sample_info_cols[3]:
                st.metric("总重量", f"{sample['total_weight']:.2f} g")

            if sample.get('description'):
                st.markdown(f"**备注：** {sample['description']}")

    st.markdown("---")

    stages = get_stages()
    stage_codes = [s['stage_code'] for s in stages]
    current_idx = stage_codes.index(task['current_stage']) if task['current_stage'] in stage_codes else 0

    st.subheader("📊 流程进度")

    progress_cols = st.columns(len(stages))
    for i, stage in enumerate(stages):
        with progress_cols[i]:
            is_done = i < current_idx
            is_current = i == current_idx

            if is_done:
                icon = "✅"
                color = "green"
            elif is_current:
                icon = "🔄"
                color = "blue"
            else:
                icon = "⏳"
                color = "gray"

            st.markdown(f"<div style='text-align: center;'>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='color: {color};'>{icon}</h3>", unsafe_allow_html=True)
            st.markdown(f"<p style='font-weight: {'bold' if is_current else 'normal'}; "
                        f"color: {color};'>{stage['stage_name']}</p>", unsafe_allow_html=True)
            st.markdown(f"</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("⚡ 任务操作")

    op_cols = st.columns(3)

    with op_cols[0]:
        with st.expander("👤 分派任务", expanded=not task.get('assigned_to')):
            users = get_all_users()
            user_options = {f"{u['full_name']} ({u['role']})": u['username'] for u in users}
            default_idx = 0
            if task.get('assigned_to'):
                for i, (k, v) in enumerate(user_options.items()):
                    if v == task['assigned_to']:
                        default_idx = i
                        break

            assignee_label = st.selectbox("选择负责人", list(user_options.keys()), index=default_idx,
                                          key="assign_user_select")
            deadline_hours = st.number_input("截止时间（小时后）", min_value=1, max_value=720, value=24, step=1,
                                             key="assign_deadline")
            assign_comment = st.text_area("分派说明", height=60, key="assign_comment")

            if st.button("确认分派", type="primary", use_container_width=True):
                assign_task(
                    task_id=task_id,
                    assignee=user_options[assignee_label],
                    assigner=st.session_state.wf_current_user,
                    comment=assign_comment,
                    deadline_hours=deadline_hours
                )
                st.success("任务分派成功！")
                st.rerun()

    with op_cols[1]:
        with st.expander("📝 处理任务", expanded=task.get('assigned_to') == st.session_state.wf_current_user):
            if task['task_status'] == 'pending':
                st.info("任务待处理，点击下方开始处理")
                start_comment = st.text_area("备注", height=60, key="start_comment")
                if st.button("🚀 开始处理", type="primary", use_container_width=True):
                    start_task(task_id, st.session_state.wf_current_user, start_comment)
                    st.success("已开始处理！")
                    st.rerun()
            elif task['task_status'] == 'in_progress':
                st.info("任务处理中，完成后提交审核")
                complete_comment = st.text_area("完成说明", height=60, key="complete_comment")
                if st.button("✅ 提交完成", type="primary", use_container_width=True):
                    has_next = complete_stage(task_id, st.session_state.wf_current_user, complete_comment)
                    if has_next:
                        st.success("当前阶段已完成，进入下一阶段！")
                    else:
                        st.success("🎉 所有阶段已完成，任务归档！")
                    st.rerun()
            elif task['task_status'] == 'returned':
                st.warning("任务已退回，请重新处理")
                start_comment = st.text_area("处理说明", height=60, key="returned_handle_comment")
                if st.button("🔄 重新开始处理", type="primary", use_container_width=True):
                    start_task(task_id, st.session_state.wf_current_user, start_comment)
                    st.success("已重新开始处理！")
                    st.rerun()
            elif task['task_status'] == 'completed':
                st.success("✅ 任务已全部完成")
            else:
                st.info("当前状态不可直接处理")

    with op_cols[2]:
        with st.expander("🔙 退回修改", expanded=False):
            stages_for_return = [s for s in stages if s['stage_code'] != task['current_stage']]
            return_options = {s['stage_name']: s['stage_code'] for s in stages_for_return}

            if return_options:
                return_stage_label = st.selectbox("退回至阶段", list(return_options.keys()),
                                                  key="return_stage")
                return_reason = st.text_area("退回原因", height=80, key="return_reason")

                if st.button("确认退回", type="secondary", use_container_width=True):
                    return_task(
                        task_id=task_id,
                        operator=st.session_state.wf_current_user,
                        return_reason=return_reason,
                        return_to_stage=return_options[return_stage_label]
                    )
                    st.warning("任务已退回！")
                    st.rerun()
            else:
                st.info("无其他阶段可退回")

    st.markdown("---")

    with st.expander("✍️ 审核签字", expanded=False):
        st.markdown("#### 审核意见")

        approval_result = st.radio(
            "审核结果",
            ["通过", "驳回"],
            horizontal=True,
            key="approval_result"
        )
        approval_comment = st.text_area("审核意见", height=80, key="approval_comment")

        if st.button("提交审核", type="primary", use_container_width=True):
            add_approval(
                task_id=task_id,
                stage_code=task['current_stage'],
                approver=st.session_state.wf_current_user,
                result=approval_result,
                comment=approval_comment
            )
            st.success("审核意见已提交！")
            st.rerun()

    st.markdown("---")
    st.subheader("📜 流程日志")

    logs = task.get('stage_logs', [])
    if not logs:
        st.info("暂无流程日志")
    else:
        log_data = []
        for log in logs:
            action_map = {
                'create': '创建',
                'assign': '分派',
                'start': '开始处理',
                'complete': '完成',
                'return': '退回',
                'update_deadline': '调整期限',
            }
            log_data.append({
                '时间': log.get('acted_at', '')[:19] if log.get('acted_at') else '',
                '阶段': get_stage_name(log.get('stage_code', '')),
                '操作': action_map.get(log.get('action', ''), log.get('action', '')),
                '状态': get_status_name(log.get('status', '')),
                '操作人': log.get('operator', ''),
                '接收人': log.get('assignee', '') or '-',
                '备注': log.get('comment', '') or '',
            })

        log_df = pd.DataFrame(log_data)
        st.dataframe(log_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("✅ 审核记录")

    approvals = task.get('approvals', [])
    if not approvals:
        st.info("暂无审核记录")
    else:
        approval_data = []
        for a in approvals:
            approver_user = get_user(a['approver'])
            approver_name = approver_user['full_name'] if approver_user else a['approver']
            approval_data.append({
                '时间': a.get('signed_at', '')[:19] if a.get('signed_at') else '',
                '阶段': get_stage_name(a.get('stage_code', '')),
                '审核人': approver_name,
                '结果': a.get('approval_result', ''),
                '意见': a.get('comment', '') or '',
            })

        approval_df = pd.DataFrame(approval_data)
        st.dataframe(approval_df, use_container_width=True, hide_index=True)


def render_collab_board():
    st.header("🎯 人员协作看板")

    users = get_all_users()
    stages = get_stages()

    col_ctrl1, col_ctrl2 = st.columns([1, 3])
    with col_ctrl1:
        view_mode = st.radio("看板视图", ["按人员", "按阶段"], horizontal=True)

    if view_mode == "按人员":
        st.markdown("### 👥 按人员分组")

        user_cols = st.columns(len(users) if users else 1)

        for i, user in enumerate(users):
            with user_cols[i]:
                st.markdown(f"#### 👤 {user['full_name']}")
                st.caption(f"{user['role']}")

                user_tasks = get_user_tasks(user['username'])
                active_tasks = [t for t in user_tasks if t['task_status'] != 'completed']

                st.metric("进行中任务", len(active_tasks))

                if not active_tasks:
                    st.info("暂无进行中任务")
                else:
                    for t in active_tasks[:8]:
                        is_overdue = False
                        if t.get('deadline') and t['task_status'] in ('pending', 'in_progress'):
                            try:
                                deadline_dt = datetime.strptime(t['deadline'], '%Y-%m-%d %H:%M:%S')
                                is_overdue = deadline_dt < datetime.now()
                            except (ValueError, TypeError):
                                pass

                        status_display = get_status_name(t['task_status']) if not is_overdue else '已超期'
                        status_color = 'red' if is_overdue else get_status_color(t['task_status'])

                        with st.container(border=True):
                            st.markdown(f"**{t['sample_no']}**")
                            st.caption(f"{get_stage_name(t['current_stage'])}")
                            st.markdown(f"<span style='color: {status_color}; font-size: 0.8em;'>"
                                        f"● {status_display}</span>", unsafe_allow_html=True)
                            if t.get('deadline'):
                                st.caption(f"截止: {t['deadline'][:16]}")

                            if st.button("查看", key=f"user_task_{t['id']}", use_container_width=True):
                                st.session_state.wf_viewing_task_id = t['id']
                                st.session_state.wf_page = "任务列表"
                                st.rerun()

                            st.markdown("")
    else:
        st.markdown("### 📊 按阶段分组")

        stage_cols = st.columns(len(stages) if stages else 1)

        for i, stage in enumerate(stages):
            with stage_cols[i]:
                st.markdown(f"#### {stage['stage_name']}")

                stage_tasks = get_all_tasks(stage=stage['stage_code'])
                active_tasks = [t for t in stage_tasks if t['task_status'] != 'completed']

                st.metric("任务数", len(active_tasks))

                if not active_tasks:
                    st.info("暂无任务")
                else:
                    for t in active_tasks[:8]:
                        is_overdue = False
                        if t.get('deadline') and t['task_status'] in ('pending', 'in_progress'):
                            try:
                                deadline_dt = datetime.strptime(t['deadline'], '%Y-%m-%d %H:%M:%S')
                                is_overdue = deadline_dt < datetime.now()
                            except (ValueError, TypeError):
                                pass

                        assignee_name = '未分派'
                        if t.get('assigned_to'):
                            user = get_user(t['assigned_to'])
                            assignee_name = user['full_name'] if user else t['assigned_to']

                        status_display = get_status_name(t['task_status']) if not is_overdue else '已超期'
                        status_color = 'red' if is_overdue else get_status_color(t['task_status'])

                        with st.container(border=True):
                            st.markdown(f"**{t['sample_no']}**")
                            st.caption(f"负责人: {assignee_name}")
                            st.markdown(f"<span style='color: {status_color}; font-size: 0.8em;'>"
                                        f"● {status_display}</span>", unsafe_allow_html=True)

                            if st.button("查看", key=f"stage_task_{t['id']}", use_container_width=True):
                                st.session_state.wf_viewing_task_id = t['id']
                                st.session_state.wf_page = "任务列表"
                                st.rerun()

                            st.markdown("")

    st.markdown("---")
    st.subheader("📋 任务负载统计")

    stats = get_workflow_statistics()
    assignee_stats = stats.get('by_assignee', {})

    if assignee_stats:
        load_data = []
        for username, count in assignee_stats.items():
            user = get_user(username)
            full_name = user['full_name'] if user else username
            load_data.append({
                '人员': full_name,
                '进行中任务数': count,
            })

        load_df = pd.DataFrame(load_data)
        st.bar_chart(load_df.set_index('人员'), use_container_width=True, height=300)
    else:
        st.info("暂无任务分派数据")


def render_workflow_stats():
    st.header("📊 流程统计分析")

    stats = get_workflow_statistics()

    st.subheader("📈 总体概览")

    metric_cols = st.columns(5)
    with metric_cols[0]:
        st.metric("总任务数", stats.get('total_tasks', 0))
    with metric_cols[1]:
        st.metric("待处理", stats.get('by_status', {}).get('pending', 0))
    with metric_cols[2]:
        st.metric("处理中", stats.get('by_status', {}).get('in_progress', 0))
    with metric_cols[3]:
        st.metric("已完成", stats.get('by_status', {}).get('completed', 0))
    with metric_cols[4]:
        st.metric("超期任务", stats.get('overdue_count', 0), delta=None)

    st.markdown("---")

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("📊 任务状态分布")
        status_data = []
        status_map = {
            'pending': '待处理',
            'in_progress': '处理中',
            'completed': '已完成',
            'returned': '已退回',
        }
        for status, count in stats.get('by_status', {}).items():
            status_data.append({
                '状态': status_map.get(status, status),
                '数量': count,
            })
        if status_data:
            status_df = pd.DataFrame(status_data)
            st.bar_chart(status_df.set_index('状态'), use_container_width=True, height=300, color='#1f77b4')
        else:
            st.info("暂无数据")

    with col_chart2:
        st.subheader("📊 阶段分布（进行中）")
        stage_data = []
        stage_map = {s['code']: s['name'] for s in WORKFLOW_STAGES}
        for stage_code, count in stats.get('by_stage', {}).items():
            stage_data.append({
                '阶段': stage_map.get(stage_code, stage_code),
                '数量': count,
            })
        if stage_data:
            stage_df = pd.DataFrame(stage_data)
            st.bar_chart(stage_df.set_index('阶段'), use_container_width=True, height=300, color='#ff7f0e')
        else:
            st.info("暂无数据")

    st.markdown("---")
    st.subheader("⏰ 阶段耗时分析")

    tasks = get_all_tasks(status='completed')
    if tasks:
        st.info(f"已完成任务共 {len(tasks)} 个，阶段耗时分析功能可扩展")
    else:
        st.info("暂无已完成任务，无法进行耗时分析")

    st.markdown("---")
    st.subheader("👥 人员工作量统计")

    users = get_all_users()
    if users:
        workload_data = []
        for user in users:
            user_tasks = get_user_tasks(user['username'])
            completed_count = len([t for t in get_all_tasks(assignee=user['username'])
                                   if t['task_status'] == 'completed'])
            active_count = len([t for t in user_tasks if t['task_status'] != 'completed'])
            workload_data.append({
                '人员': user['full_name'],
                '角色': user.get('role', ''),
                '进行中任务': active_count,
                '已完成任务': completed_count,
            })

        workload_df = pd.DataFrame(workload_data)
        st.dataframe(workload_df, use_container_width=True, hide_index=True)

        st.bar_chart(workload_df.set_index('人员')[['进行中任务', '已完成任务']],
                     use_container_width=True, height=350)
    else:
        st.info("暂无人员数据")


def render_overdue_alert():
    st.header("⏰ 超期任务提醒")

    overdue_tasks = get_overdue_tasks()

    if not overdue_tasks:
        st.success("🎉 暂无超期任务！所有任务均在处理期限内。")
        return

    st.warning(f"⚠️ 当前共有 {len(overdue_tasks)} 个超期任务，请及时处理！")

    display_data = []
    for t in overdue_tasks:
        try:
            deadline_dt = datetime.strptime(t['deadline'], '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            overdue_hours = int((now - deadline_dt).total_seconds() / 3600)
            overdue_days = overdue_hours // 24
            overdue_remainder = overdue_hours % 24
            if overdue_days > 0:
                overdue_str = f"{overdue_days}天{overdue_remainder}小时"
            else:
                overdue_str = f"{overdue_remainder}小时"
        except (ValueError, TypeError):
            overdue_str = "未知"

        assignee_name = '未分派'
        if t.get('assigned_to'):
            user = get_user(t['assigned_to'])
            assignee_name = user['full_name'] if user else t['assigned_to']

        display_data.append({
            '任务ID': t['id'],
            '样本编号': t['sample_no'],
            '采样点': t.get('sampling_site', ''),
            '当前阶段': get_stage_name(t['current_stage']),
            '状态': get_status_name(t['task_status']),
            '优先级': get_priority_name(t.get('priority', 'normal')),
            '负责人': assignee_name,
            '截止时间': t.get('deadline', '')[:19] if t.get('deadline') else '',
            '超期时长': overdue_str,
            '分组': t.get('group_name', ''),
        })

    df = pd.DataFrame(display_data)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)

    st.markdown("---")
    st.subheader("📌 快速操作")

    task_options = {f"{t['sample_no']} - {get_stage_name(t['current_stage'])} - 超期{display_data[i]['超期时长']}": t['id']
                    for i, t in enumerate(overdue_tasks)}

    col_op1, col_op2 = st.columns([3, 1])
    with col_op1:
        selected_task_label = st.selectbox("选择任务", list(task_options.keys()),
                                           label_visibility="collapsed")
        selected_task_id = task_options[selected_task_label]

    with col_op2:
        if st.button("📋 查看并处理", use_container_width=True, type="primary"):
            st.session_state.wf_viewing_task_id = selected_task_id
            st.session_state.wf_page = "任务列表"
            st.rerun()

    st.markdown("---")
    st.subheader("📊 超期任务统计")

    col_s1, col_s2, col_s3 = st.columns(3)

    with col_s1:
        stage_overdue = {}
        for t in overdue_tasks:
            stage = get_stage_name(t['current_stage'])
            stage_overdue[stage] = stage_overdue.get(stage, 0) + 1
        st.metric("涉及阶段数", len(stage_overdue))

    with col_s2:
        assignee_overdue = {}
        for t in overdue_tasks:
            assignee = t.get('assigned_to') or '未分派'
            assignee_overdue[assignee] = assignee_overdue.get(assignee, 0) + 1
        st.metric("涉及人员数", len(assignee_overdue))

    with col_s3:
        high_priority_count = len([t for t in overdue_tasks if t.get('priority') == 'high'])
        st.metric("高优先级超期", high_priority_count)


def render_create_task_from_sample(sample_id=None):
    st.subheader("➕ 为样本创建任务")

    samples = get_all_samples()
    if not samples:
        st.info("暂无样本，请先创建样本。")
        return

    sample_options = {f"{s['sample_no']} - {s['sampling_site']}": s['id'] for s in samples}

    default_idx = 0
    if sample_id:
        for i, (k, v) in enumerate(sample_options.items()):
            if v == sample_id:
                default_idx = i
                break

    selected_sample_label = st.selectbox("选择样本", list(sample_options.keys()), index=default_idx)
    selected_sample_id = sample_options[selected_sample_label]

    existing_task = get_task_by_sample(selected_sample_id)
    if existing_task:
        st.warning(f"⚠️ 该样本已有进行中的任务（状态：{get_status_name(existing_task['task_status'])}）")
        if st.button("查看现有任务"):
            st.session_state.wf_viewing_task_id = existing_task['id']
            st.session_state.wf_page = "任务列表"
            st.rerun()
        return

    priority_options = {
        '高': 'high',
        '普通': 'normal',
        '低': 'low',
    }
    priority_label = st.selectbox("任务优先级", list(priority_options.keys()), index=1)
    priority = priority_options[priority_label]

    deadline_hours = st.number_input("第一阶段截止时间（小时后）", min_value=1, max_value=720, value=24, step=1)
    description = st.text_area("任务描述", height=80)

    if st.button("创建任务", type="primary", use_container_width=True):
        task_id = create_task_for_sample(
            sample_id=selected_sample_id,
            sample_no=selected_sample_label.split(' - ')[0],
            created_by=st.session_state.wf_current_user,
            description=description,
            priority=priority,
            deadline_hours=deadline_hours,
        )
        st.success(f"任务创建成功！任务ID: {task_id}")
        st.session_state.wf_viewing_task_id = task_id
        st.rerun()


def render_workflow_main():
    init_session_state()
    init_workflow_db()

    render_workflow_sidebar()

    page = st.session_state.wf_page

    if page == "任务列表":
        if st.session_state.wf_viewing_task_id:
            render_task_detail()
        else:
            render_task_list()
    elif page == "协作看板":
        render_collab_board()
    elif page == "流程统计":
        render_workflow_stats()
    elif page == "超期提醒":
        render_overdue_alert()
    else:
        render_task_list()
