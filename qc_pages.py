import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import io

from qc_db import (
    init_qc_db,
    create_batch, get_batch, get_all_batches, update_batch, delete_batch,
    add_sample_to_batch, remove_sample_from_batch, get_batch_samples,
    get_batch_name,
    create_instrument, get_instrument, get_all_instruments, update_instrument,
    delete_instrument,
    add_calibration, get_instrument_calibrations, get_calibrations_needing_reminder,
    get_overdue_calibrations, get_calibration_status_name,
    add_parallel_sample, get_parallel_samples, calculate_parallel_stats,
    get_parallel_type_name,
    create_alert, get_alerts, acknowledge_alert, get_alert_summary,
    get_alert_level_name, check_and_create_sieve_recovery_alert,
    create_retest_request, get_retest_requests, get_retest_request_by_no,
    approve_retest, reject_retest, complete_retest, get_retest_status_name,
    get_qc_dashboard_stats, get_qc_standards,
)

from db import get_all_samples, get_sample


def render_qc_dashboard():
    st.header("📊 质量控制看板")

    stats = get_qc_dashboard_stats()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("实验批次总数", stats['batches']['total'])
        st.caption(f"进行中: {stats['batches']['in_progress']} | 已完成: {stats['batches']['completed']}")

    with col2:
        inst = stats['instruments']
        st.metric("在用仪器数", inst['active'])
        st.caption(f"校准到期: {inst['calibration_due']}台 | 超期: {inst['overdue']}台")

    with col3:
        pq = stats['parallel_qc']
        pass_rate = f"{pq['pass_rate']:.1f}%" if pq['total'] > 0 else "—"
        st.metric("平行样合格率", pass_rate)
        st.caption(f"总次数: {pq['total']} | 不合格: {pq['failed']}")

    with col4:
        alerts = stats['alerts']
        unack = alerts.get('unacknowledged_count', 0)
        st.metric("未处理预警", unack)
        error_count = alerts.get('by_level_unack', {}).get('error', 0)
        warning_count = alerts.get('by_level_unack', {}).get('warning', 0)
        st.caption(f"严重: {error_count} | 警告: {warning_count}")

    st.markdown("---")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("🔔 最新质量预警")
        recent_alerts = get_alerts(limit=10)
        if not recent_alerts:
            st.info("暂无预警记录")
        else:
            alert_rows = []
            for a in recent_alerts:
                level_color = {
                    'error': '🔴',
                    'warning': '🟡',
                    'info': '🔵',
                }.get(a['alert_level'], '⚪')
                status = '✅' if a['is_acknowledged'] else '⏳'
                alert_rows.append({
                    '状态': status,
                    '级别': f"{level_color} {get_alert_level_name(a['alert_level'])}",
                    '标题': a['title'],
                    '关联对象': a.get('related_entity_name', ''),
                    '创建时间': a['created_at'][:19] if a.get('created_at') else '',
                    'id': a['id'],
                })

            df = pd.DataFrame(alert_rows)
            st.dataframe(df.drop(columns=['id']), use_container_width=True, hide_index=True)

            if st.button("查看全部预警 →"):
                st.session_state.current_page = "质量预警"
                st.rerun()

    with col_right:
        st.subheader("📋 待办事项")

        pending_retests = get_retest_requests(status='pending')
        if pending_retests:
            st.warning(f"🔄 有 {len(pending_retests)} 个复测申请待审批")
            if st.button("去审批", use_container_width=True):
                st.session_state.current_page = "复测申请"
                st.rerun()

        cal_due = get_calibrations_needing_reminder(30)
        if cal_due:
            st.warning(f"🔧 有 {len(cal_due)} 台仪器校准即将到期")
            if st.button("查看仪器", use_container_width=True):
                st.session_state.current_page = "仪器管理"
                st.rerun()

        overdue_cal = get_overdue_calibrations()
        if overdue_cal:
            st.error(f"⚠️ 有 {len(overdue_cal)} 台仪器校准已超期")

    st.markdown("---")
    st.subheader("📈 近期质量趋势")

    trend_days = st.selectbox("查看最近", [7, 14, 30, 90], index=2, key="qc_trend_days")
    today = datetime.now().date()
    date_from = (today - timedelta(days=trend_days)).strftime('%Y-%m-%d')

    all_parallel = get_parallel_samples(date_from=date_from)
    if all_parallel:
        df = pd.DataFrame(all_parallel)
        df['date'] = pd.to_datetime(df['comparison_date']).dt.date

        daily_stats = df.groupby('date').agg(
            total=('id', 'count'),
            passed=('is_pass', 'sum'),
        ).reset_index()
        daily_stats['pass_rate'] = daily_stats['passed'] / daily_stats['total'] * 100

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=daily_stats['date'],
                y=daily_stats['total'],
                name='总检测数',
                marker_color='#1f77b4',
            )
        )
        fig.add_trace(
            go.Scatter(
                x=daily_stats['date'],
                y=daily_stats['pass_rate'],
                name='合格率(%)',
                yaxis='y2',
                line=dict(color='#ff7f0e', width=2),
                mode='lines+markers',
            )
        )
        fig.update_layout(
            title='平行样检测趋势',
            yaxis=dict(title='检测数量'),
            yaxis2=dict(title='合格率(%)', overlaying='y', side='right', range=[0, 105]),
            height=350,
            legend=dict(orientation='h', y=-0.1),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暂无平行样检测数据")


def render_batch_management():
    st.header("📦 实验批次管理")

    if 'qc_view' not in st.session_state:
        st.session_state.qc_view = 'list'
    if 'qc_viewing_batch_id' not in st.session_state:
        st.session_state.qc_viewing_batch_id = None

    if st.session_state.qc_view == 'list':
        _render_batch_list()
    elif st.session_state.qc_view == 'detail':
        _render_batch_detail()
    elif st.session_state.qc_view == 'new':
        _render_batch_new()


def _render_batch_list():
    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader("批次列表")
    with col2:
        if st.button("➕ 新建批次", type="primary", use_container_width=True):
            st.session_state.qc_view = 'new'
            st.rerun()

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        status_filter = st.selectbox(
            "状态筛选",
            ["全部"] + list(["planning", "in_progress", "completed", "cancelled"]),
            format_func=lambda x: "全部" if x == "全部" else get_batch_name(x),
            index=0,
        )
    with col_f2:
        type_filter = st.selectbox(
            "类型筛选",
            ["全部", "sieving", "chemical", "physical"],
            format_func=lambda x: {
                "全部": "全部",
                "sieving": "筛分实验",
                "chemical": "化学分析",
                "physical": "物理检测",
            }.get(x, x),
            index=0,
        )
    with col_f3:
        search_text = st.text_input("搜索批次编号/名称", "")

    batches = get_all_batches(
        status=status_filter if status_filter != "全部" else None,
        batch_type=type_filter if type_filter != "全部" else None,
    )

    if search_text.strip():
        search = search_text.strip().lower()
        batches = [b for b in batches
                   if search in str(b.get('batch_no', '')).lower()
                   or search in str(b.get('batch_name', '')).lower()]

    if not batches:
        st.info("暂无实验批次，点击「新建批次」开始创建。")
        return

    display_data = []
    for b in batches:
        status_name = get_batch_name(b.get('status', 'planning'))
        status_color = {
            'planning': 'gray',
            'in_progress': 'orange',
            'completed': 'green',
            'cancelled': 'red',
        }.get(b.get('status', ''), 'gray')

        display_data.append({
            '批次编号': b.get('batch_no', ''),
            '批次名称': b.get('batch_name', ''),
            '类型': {
                'sieving': '筛分实验',
                'chemical': '化学分析',
                'physical': '物理检测',
            }.get(b.get('batch_type', ''), b.get('batch_type', '')),
            '状态': status_name,
            '_status_code': b.get('status', ''),
            '样本数': b.get('total_samples', 0),
            '操作员': b.get('operator', ''),
            '开始日期': b.get('start_date', ''),
            '结束日期': b.get('end_date', ''),
            'id': b['id'],
        })

    df = pd.DataFrame(display_data)

    def style_status(row):
        color_map = {
            'planning': 'color: gray; font-weight: bold;',
            'in_progress': 'color: orange; font-weight: bold;',
            'completed': 'color: green; font-weight: bold;',
            'cancelled': 'color: red; font-weight: bold;',
        }
        return [color_map.get(row['_status_code'], '') for _ in row]

    styled_df = df.drop(columns=['id', '_status_code']).style.apply(style_status, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    st.markdown("### 操作")
    col1, col2, col3 = st.columns([2, 1, 1])

    batch_options = {f"{b['batch_no']} - {b.get('batch_name', '')}": b['id'] for b in batches}
    with col1:
        selected = st.selectbox("选择批次", list(batch_options.keys()), label_visibility="collapsed")
        selected_id = batch_options[selected]

    with col2:
        if st.button("查看详情", use_container_width=True):
            st.session_state.qc_viewing_batch_id = selected_id
            st.session_state.qc_view = 'detail'
            st.rerun()

    with col3:
        if st.button("删除批次", use_container_width=True):
            if delete_batch(selected_id):
                st.success("批次已删除")
                st.rerun()
            else:
                st.error("删除失败")


def _render_batch_new():
    st.subheader("➕ 新建实验批次")

    with st.form("new_batch_form"):
        col1, col2 = st.columns(2)
        with col1:
            batch_no = st.text_input("批次编号 *", value=f"B{datetime.now().strftime('%Y%m%d')}")
            batch_name = st.text_input("批次名称")
            batch_type = st.selectbox(
                "批次类型",
                ["sieving", "chemical", "physical"],
                format_func=lambda x: {
                    'sieving': '筛分实验',
                    'chemical': '化学分析',
                    'physical': '物理检测',
                }.get(x, x),
                index=0,
            )
            status = st.selectbox(
                "初始状态",
                ["planning", "in_progress"],
                format_func=lambda x: get_batch_name(x),
                index=0,
            )
        with col2:
            operator = st.text_input("操作员")
            start_date = st.date_input("开始日期", value=datetime.now().date())
            end_date = st.date_input("预计结束日期",
                                     value=datetime.now().date() + timedelta(days=3))

        description = st.text_area("批次描述", height=100)

        col_sub1, col_sub2 = st.columns([1, 1])
        with col_sub1:
            submitted = st.form_submit_button("创建批次", type="primary", use_container_width=True)
        with col_sub2:
            if st.form_submit_button("取消", use_container_width=True):
                st.session_state.qc_view = 'list'
                st.rerun()

        if submitted:
            if not batch_no.strip():
                st.error("请输入批次编号")
            else:
                batch_id = create_batch(
                    batch_no=batch_no.strip(),
                    batch_name=batch_name.strip() if batch_name.strip() else None,
                    batch_type=batch_type,
                    status=status,
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d'),
                    operator=operator.strip() if operator.strip() else None,
                    description=description.strip() if description.strip() else None,
                )
                st.success(f"批次 {batch_no} 创建成功！")
                st.session_state.qc_viewing_batch_id = batch_id
                st.session_state.qc_view = 'detail'
                st.rerun()


def _render_batch_detail():
    batch_id = st.session_state.qc_viewing_batch_id
    batch = get_batch(batch_id)

    if not batch:
        st.error("批次不存在")
        if st.button("返回列表"):
            st.session_state.qc_view = 'list'
            st.rerun()
        return

    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader(f"📦 {batch['batch_no']} - {batch.get('batch_name', '')}")
    with col2:
        if st.button("← 返回列表", use_container_width=True):
            st.session_state.qc_view = 'list'
            st.rerun()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("状态", get_batch_name(batch.get('status', '')))
    with col2:
        st.metric("样本数", batch.get('total_samples', 0))
    with col3:
        st.metric("操作员", batch.get('operator') or '未指定')
    with col4:
        st.metric("类型", {
            'sieving': '筛分实验',
            'chemical': '化学分析',
            'physical': '物理检测',
        }.get(batch.get('batch_type', ''), batch.get('batch_type', '')))

    with st.expander("📝 批次信息", expanded=False):
        st.caption(f"开始日期: {batch.get('start_date', '未设置')}")
        st.caption(f"结束日期: {batch.get('end_date', '未设置')}")
        st.caption(f"创建时间: {batch.get('created_at', '')[:19]}")
        if batch.get('description'):
            st.markdown(f"**描述：** {batch['description']}")

    st.markdown("---")
    st.subheader("📋 批次样本")

    all_samples = get_all_samples()
    batch_sample_ids = {s['sample_id'] for s in batch.get('samples', [])}
    available_samples = [s for s in all_samples if s['id'] not in batch_sample_ids]

    with st.expander("➕ 添加样本到批次", expanded=False):
        if not available_samples:
            st.info("所有样本都已在批次中")
        else:
            sample_options = {f"{s['sample_no']} - {s['sampling_site']}": s['id']
                             for s in available_samples}
            selected_samples = st.multiselect(
                "选择要添加的样本",
                list(sample_options.keys()),
            )
            position_start = st.number_input("起始位置编号", min_value=1, value=len(batch_sample_ids) + 1)

            if st.button("添加到批次", type="primary"):
                added = 0
                for i, sel in enumerate(selected_samples):
                    sid = sample_options[sel]
                    sample = next((s for s in all_samples if s['id'] == sid), None)
                    if sample:
                        if add_sample_to_batch(
                            batch_id, sid, sample['sample_no'],
                            position_no=position_start + i
                        ):
                            added += 1
                if added > 0:
                    st.success(f"成功添加 {added} 个样本")
                    st.rerun()
                else:
                    st.warning("未添加任何样本")

    samples = batch.get('samples', [])
    if not samples:
        st.info("暂无样本，请添加样本到批次中")
    else:
        display_data = []
        for i, s in enumerate(samples):
            display_data.append({
                '序号': s.get('position_no') or (i + 1),
                '样本编号': s.get('sample_no', ''),
                '采样点': s.get('sampling_site', ''),
                '总重量(g)': s.get('total_weight', ''),
                '分组': s.get('group_name', ''),
                '添加时间': s.get('added_at', '')[:19] if s.get('added_at') else '',
                'sample_id': s.get('sample_id'),
            })

        df = pd.DataFrame(display_data)
        st.dataframe(df.drop(columns=['sample_id']), use_container_width=True, hide_index=True)

        col1, col2 = st.columns([2, 1])
        with col1:
            sample_options = {f"{s['sample_no']} - {s.get('sampling_site', '')}": s['sample_id']
                             for s in samples}
            selected = st.selectbox("选择样本操作", list(sample_options.keys()),
                                   label_visibility="collapsed")
            selected_sid = sample_options[selected]
        with col2:
            if st.button("从批次移除", use_container_width=True):
                if remove_sample_from_batch(batch_id, selected_sid):
                    st.success("已移除样本")
                    st.rerun()

    st.markdown("---")
    st.subheader("✏️ 编辑批次状态")

    col1, col2, col3 = st.columns(3)
    with col1:
        new_status = st.selectbox(
            "更新状态",
            ["planning", "in_progress", "completed", "cancelled"],
            format_func=lambda x: get_batch_name(x),
            index=["planning", "in_progress", "completed", "cancelled"].index(batch.get('status', 'planning')),
        )
    with col2:
        new_operator = st.text_input("操作员", value=batch.get('operator') or '')
    with col3:
        st.text("")
        if st.button("保存修改", type="primary", use_container_width=True):
            update_batch(batch_id, status=new_status,
                        operator=new_operator.strip() if new_operator.strip() else None)
            st.success("批次信息已更新")
            st.rerun()


def render_instrument_management():
    st.header("🔬 仪器管理")

    if 'inst_view' not in st.session_state:
        st.session_state.inst_view = 'list'
    if 'viewing_inst_id' not in st.session_state:
        st.session_state.viewing_inst_id = None

    if st.session_state.inst_view == 'list':
        _render_instrument_list()
    elif st.session_state.inst_view == 'detail':
        _render_instrument_detail()
    elif st.session_state.inst_view == 'new':
        _render_instrument_new()


def _render_instrument_list():
    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader("仪器列表")
    with col2:
        if st.button("➕ 添加仪器", type="primary", use_container_width=True):
            st.session_state.inst_view = 'new'
            st.rerun()

    overdue = get_overdue_calibrations()
    cal_due = get_calibrations_needing_reminder(30)

    if overdue:
        st.error(f"⚠️ {len(overdue)} 台仪器校准已超期！")
    if cal_due and not overdue:
        st.warning(f"🔧 {len(cal_due)} 台仪器校准将在30天内到期")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filter = st.selectbox(
            "状态筛选",
            ["全部", "active", "maintenance", "retired"],
            format_func=lambda x: {
                "全部": "全部",
                "active": "在用",
                "maintenance": "维修中",
                "retired": "已停用",
            }.get(x, x),
            index=0,
        )
    with col_f2:
        type_filter = st.selectbox(
            "类型筛选",
            ["全部", "sieve", "balance", "shaker", "oven", "other"],
            format_func=lambda x: {
                "全部": "全部",
                "sieve": "试验筛",
                "balance": "天平",
                "shaker": "振筛机",
                "oven": "烘箱",
                "other": "其他",
            }.get(x, x),
            index=0,
        )

    instruments = get_all_instruments(
        status=status_filter if status_filter != "全部" else None,
        instrument_type=type_filter if type_filter != "全部" else None,
    )

    if not instruments:
        st.info("暂无仪器，点击「添加仪器」开始录入。")
        return

    display_data = []
    for inst in instruments:
        next_cal = inst.get('next_calibration_date')
        today = datetime.now().date()
        cal_status = '正常'
        cal_color = 'green'
        if next_cal:
            try:
                cal_date = datetime.strptime(next_cal, '%Y-%m-%d').date()
                if cal_date < today:
                    cal_status = '已超期'
                    cal_color = 'red'
                elif (cal_date - today).days <= 30:
                    cal_status = '即将到期'
                    cal_color = 'orange'
            except ValueError:
                pass

        display_data.append({
            '仪器编号': inst.get('instrument_code', ''),
            '仪器名称': inst.get('instrument_name', ''),
            '类型': {
                'sieve': '试验筛',
                'balance': '天平',
                'shaker': '振筛机',
                'oven': '烘箱',
                'other': '其他',
            }.get(inst.get('instrument_type', ''), inst.get('instrument_type', '')),
            '型号': inst.get('model', ''),
            '位置': inst.get('location', ''),
            '校准周期(天)': inst.get('calibration_cycle_days', ''),
            '上次校准': inst.get('last_calibration_date') or '未校准',
            '下次校准': next_cal or '未设置',
            '校准状态': cal_status,
            '_cal_color': cal_color,
            '状态': {
                'active': '在用',
                'maintenance': '维修中',
                'retired': '已停用',
            }.get(inst.get('status', ''), inst.get('status', '')),
            'id': inst['id'],
        })

    df = pd.DataFrame(display_data)

    def style_cal(row):
        return ['' if col != '校准状态' else f'color: {row["_cal_color"]}; font-weight: bold;'
                for col in df.columns]

    styled_df = df.drop(columns=['id', '_cal_color']).style.apply(style_cal, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    st.markdown("### 操作")
    col1, col2 = st.columns([2, 1])
    inst_options = {f"{inst['instrument_code']} - {inst['instrument_name']}": inst['id']
                   for inst in instruments}
    with col1:
        selected = st.selectbox("选择仪器", list(inst_options.keys()), label_visibility="collapsed")
        selected_id = inst_options[selected]
    with col2:
        if st.button("查看详情", use_container_width=True):
            st.session_state.viewing_inst_id = selected_id
            st.session_state.inst_view = 'detail'
            st.rerun()


def _render_instrument_new():
    st.subheader("➕ 添加仪器")

    with st.form("new_inst_form"):
        col1, col2 = st.columns(2)
        with col1:
            inst_code = st.text_input("仪器编号 *")
            inst_name = st.text_input("仪器名称 *")
            inst_type = st.selectbox(
                "仪器类型",
                ["sieve", "balance", "shaker", "oven", "other"],
                format_func=lambda x: {
                    'sieve': '试验筛',
                    'balance': '天平',
                    'shaker': '振筛机',
                    'oven': '烘箱',
                    'other': '其他',
                }.get(x, x),
            )
            model = st.text_input("型号")
            manufacturer = st.text_input("生产厂家")
        with col2:
            serial_no = st.text_input("序列号")
            location = st.text_input("存放位置")
            cal_cycle = st.number_input("校准周期(天)", min_value=1, value=365)
            status = st.selectbox(
                "状态",
                ["active", "maintenance", "retired"],
                format_func=lambda x: {
                    'active': '在用',
                    'maintenance': '维修中',
                    'retired': '已停用',
                }.get(x, x),
            )

        description = st.text_area("备注", height=80)

        col_sub1, col_sub2 = st.columns([1, 1])
        with col_sub1:
            submitted = st.form_submit_button("添加仪器", type="primary", use_container_width=True)
        with col_sub2:
            if st.form_submit_button("取消", use_container_width=True):
                st.session_state.inst_view = 'list'
                st.rerun()

        if submitted:
            if not inst_code.strip() or not inst_name.strip():
                st.error("请填写仪器编号和名称")
            else:
                inst_id = create_instrument(
                    instrument_code=inst_code.strip(),
                    instrument_name=inst_name.strip(),
                    instrument_type=inst_type,
                    model=model.strip() if model.strip() else None,
                    manufacturer=manufacturer.strip() if manufacturer.strip() else None,
                    serial_no=serial_no.strip() if serial_no.strip() else None,
                    location=location.strip() if location.strip() else None,
                    calibration_cycle_days=cal_cycle,
                    description=description.strip() if description.strip() else None,
                )
                if inst_id:
                    st.success(f"仪器 {inst_name} 添加成功！")
                    st.session_state.viewing_inst_id = inst_id
                    st.session_state.inst_view = 'detail'
                    st.rerun()
                else:
                    st.error("仪器编号已存在")


def _render_instrument_detail():
    inst_id = st.session_state.viewing_inst_id
    instrument = get_instrument(inst_id)

    if not instrument:
        st.error("仪器不存在")
        if st.button("返回列表"):
            st.session_state.inst_view = 'list'
            st.rerun()
        return

    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader(f"🔬 {instrument['instrument_code']} - {instrument['instrument_name']}")
    with col2:
        if st.button("← 返回列表", use_container_width=True):
            st.session_state.inst_view = 'list'
            st.rerun()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("类型", {
            'sieve': '试验筛',
            'balance': '天平',
            'shaker': '振筛机',
            'oven': '烘箱',
            'other': '其他',
        }.get(instrument.get('instrument_type', ''), instrument.get('instrument_type', '')))
    with col2:
        st.metric("状态", {
            'active': '在用',
            'maintenance': '维修中',
            'retired': '已停用',
        }.get(instrument.get('status', ''), instrument.get('status', '')))
    with col3:
        st.metric("校准周期", f"{instrument.get('calibration_cycle_days', 0)}天")
    with col4:
        next_cal = instrument.get('next_calibration_date')
        if next_cal:
            today = datetime.now().date()
            try:
                cal_date = datetime.strptime(next_cal, '%Y-%m-%d').date()
                days_left = (cal_date - today).days
                st.metric("距离下次校准", f"{days_left}天")
            except ValueError:
                st.metric("下次校准", next_cal)
        else:
            st.metric("下次校准", "未设置")

    with st.expander("📋 基本信息", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"型号: {instrument.get('model') or '未记录'}")
            st.caption(f"生产厂家: {instrument.get('manufacturer') or '未记录'}")
            st.caption(f"序列号: {instrument.get('serial_no') or '未记录'}")
        with col2:
            st.caption(f"存放位置: {instrument.get('location') or '未记录'}")
            st.caption(f"上次校准: {instrument.get('last_calibration_date') or '未校准'}")
            st.caption(f"创建时间: {instrument.get('created_at', '')[:19]}")
        if instrument.get('description'):
            st.markdown(f"**备注：** {instrument['description']}")

    st.markdown("---")
    st.subheader("📝 校准记录")

    with st.expander("➕ 添加校准记录", expanded=False):
        with st.form("add_cal_form"):
            col1, col2 = st.columns(2)
            with col1:
                cal_date = st.date_input("校准日期", value=datetime.now().date())
                cal_type = st.selectbox(
                    "校准类型",
                    ["routine", "special", "after_repair", "new"],
                    format_func=lambda x: {
                        'routine': '日常校准',
                        'special': '专项校准',
                        'after_repair': '维修后校准',
                        'new': '新设备校准',
                    }.get(x, x),
                )
                status = st.selectbox(
                    "校准结果",
                    ["pending", "passed", "failed"],
                    format_func=lambda x: get_calibration_status_name(x),
                    index=1,
                )
                calibrator = st.text_input("校准人员/机构")
            with col2:
                cert_no = st.text_input("证书编号")
                cal_method = st.text_input("校准方法")
                std_ref = st.text_input("标准器/参考标准")
                uncertainty = st.number_input("测量不确定度", min_value=0.0, step=0.001)
                cost = st.number_input("校准费用(元)", min_value=0.0, step=10.0)

            pass_criteria = st.text_input("合格判定标准")
            conclusion = st.text_area("校准结论", height=80)

            cal_cycle = instrument.get('calibration_cycle_days', 365)
            next_cal_default = cal_date + timedelta(days=cal_cycle)
            next_cal_date = st.date_input("下次校准日期", value=next_cal_default)

            remarks = st.text_area("备注", height=60)

            if st.form_submit_button("保存校准记录", type="primary"):
                add_calibration(
                    instrument_id=inst_id,
                    calibration_date=cal_date.strftime('%Y-%m-%d'),
                    calibration_type=cal_type,
                    status=status,
                    calibrator=calibrator.strip() if calibrator.strip() else None,
                    certificate_no=cert_no.strip() if cert_no.strip() else None,
                    calibration_method=cal_method.strip() if cal_method.strip() else None,
                    standard_reference=std_ref.strip() if std_ref.strip() else None,
                    uncertainty=uncertainty if uncertainty > 0 else None,
                    pass_criteria=pass_criteria.strip() if pass_criteria.strip() else None,
                    conclusion=conclusion.strip() if conclusion.strip() else None,
                    next_calibration_date=next_cal_date.strftime('%Y-%m-%d'),
                    cost=cost if cost > 0 else None,
                    remarks=remarks.strip() if remarks.strip() else None,
                )
                st.success("校准记录已添加")
                st.rerun()

    calibrations = instrument.get('calibrations', [])
    if not calibrations:
        st.info("暂无校准记录")
    else:
        display_data = []
        for cal in calibrations:
            status_name = get_calibration_status_name(cal.get('status', ''))
            status_color = {
                'pending': 'gray',
                'in_progress': 'orange',
                'passed': 'green',
                'failed': 'red',
            }.get(cal.get('status', ''), 'gray')

            display_data.append({
                '校准日期': cal.get('calibration_date', ''),
                '类型': {
                    'routine': '日常校准',
                    'special': '专项校准',
                    'after_repair': '维修后校准',
                    'new': '新设备校准',
                }.get(cal.get('calibration_type', ''), cal.get('calibration_type', '')),
                '状态': status_name,
                '_status_color': status_color,
                '校准人/机构': cal.get('calibrator') or '',
                '证书编号': cal.get('certificate_no') or '',
                '不确定度': cal.get('uncertainty') or '',
                '下次校准': cal.get('next_calibration_date') or '',
                'id': cal['id'],
            })

        df = pd.DataFrame(display_data)

        def style_status(row):
            return ['' if col != '状态' else f'color: {row["_status_color"]}; font-weight: bold;'
                    for col in df.columns]

        styled_df = df.drop(columns=['id', '_status_color']).style.apply(style_status, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("✏️ 编辑仪器信息")

    with st.expander("修改仪器信息", expanded=False):
        with st.form("edit_inst_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("仪器名称", value=instrument['instrument_name'])
                new_type = st.selectbox(
                    "仪器类型",
                    ["sieve", "balance", "shaker", "oven", "other"],
                    index=["sieve", "balance", "shaker", "oven", "other"].index(
                        instrument.get('instrument_type', 'other')
                    ),
                    format_func=lambda x: {
                        'sieve': '试验筛',
                        'balance': '天平',
                        'shaker': '振筛机',
                        'oven': '烘箱',
                        'other': '其他',
                    }.get(x, x),
                )
                new_model = st.text_input("型号", value=instrument.get('model') or '')
                new_manufacturer = st.text_input("生产厂家", value=instrument.get('manufacturer') or '')
            with col2:
                new_location = st.text_input("存放位置", value=instrument.get('location') or '')
                new_cycle = st.number_input(
                    "校准周期(天)",
                    min_value=1,
                    value=int(instrument.get('calibration_cycle_days', 365))
                )
                new_status = st.selectbox(
                    "状态",
                    ["active", "maintenance", "retired"],
                    index=["active", "maintenance", "retired"].index(
                        instrument.get('status', 'active')
                    ),
                    format_func=lambda x: {
                        'active': '在用',
                        'maintenance': '维修中',
                        'retired': '已停用',
                    }.get(x, x),
                )
                new_serial = st.text_input("序列号", value=instrument.get('serial_no') or '')

            new_desc = st.text_area("备注", value=instrument.get('description') or '', height=80)

            if st.form_submit_button("保存修改", type="primary"):
                update_instrument(
                    inst_id,
                    instrument_name=new_name.strip(),
                    instrument_type=new_type,
                    model=new_model.strip() if new_model.strip() else None,
                    manufacturer=new_manufacturer.strip() if new_manufacturer.strip() else None,
                    serial_no=new_serial.strip() if new_serial.strip() else None,
                    location=new_location.strip() if new_location.strip() else None,
                    calibration_cycle_days=new_cycle,
                    status=new_status,
                    description=new_desc.strip() if new_desc.strip() else None,
                )
                st.success("仪器信息已更新")
                st.rerun()


def render_parallel_qc():
    st.header("⚖️ 平行样/重复样对比")

    tab1, tab2, tab3 = st.tabs(["对比记录", "新增对比", "统计分析"])

    with tab1:
        _render_parallel_list()

    with tab2:
        _render_parallel_new()

    with tab3:
        _render_parallel_stats()


def _render_parallel_list():
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        type_filter = st.selectbox(
            "类型筛选",
            ["全部", "duplicate", "parallel", "blank", "standard"],
            format_func=lambda x: "全部" if x == "全部" else get_parallel_type_name(x),
            index=0,
            key="pl_type_filter",
        )
    with col_f2:
        result_filter = st.selectbox(
            "结果筛选",
            ["全部", "passed", "failed"],
            format_func=lambda x: {
                "全部": "全部",
                "passed": "合格",
                "failed": "不合格",
            }.get(x, x),
            index=0,
            key="pl_result_filter",
        )
    with col_f3:
        param_filter = st.selectbox(
            "参数筛选",
            ["全部", "D50", "D10", "D90", "回收率"],
            index=0,
            key="pl_param_filter",
        )

    records = get_parallel_samples(
        parallel_type=type_filter if type_filter != "全部" else None,
        is_pass=True if result_filter == "passed" else (False if result_filter == "failed" else None),
    )

    if param_filter != "全部":
        records = [r for r in records if r.get('parameter') == param_filter]

    if not records:
        st.info("暂无对比记录，点击「新增对比」开始录入。")
        return

    display_data = []
    for r in records:
        is_pass = r.get('is_pass') == 1
        pass_label = "✅ 合格" if is_pass else "❌ 不合格"
        pass_color = "green" if is_pass else "red"

        display_data.append({
            '对比日期': r.get('comparison_date', ''),
            '类型': get_parallel_type_name(r.get('parallel_type', '')),
            '参数': r.get('parameter', ''),
            '原始样本': r.get('parent_sample_no', ''),
            '对比样本': r.get('parallel_sample_no') or '—',
            '原始值': f"{r['original_value']:.4f}" if r.get('original_value') is not None else '—',
            '对比值': f"{r['parallel_value']:.4f}" if r.get('parallel_value') is not None else '—',
            '绝对偏差': f"{r['difference']:.4f}" if r.get('difference') is not None else '—',
            '相对偏差(%)': f"{r['relative_deviation']:.2f}" if r.get('relative_deviation') is not None else '—',
            '允许偏差(%)': r.get('tolerance_pct', '—'),
            '结果': pass_label,
            '_pass_color': pass_color,
            '操作员': r.get('operator') or '',
            'id': r['id'],
        })

    df = pd.DataFrame(display_data)

    def style_result(row):
        return ['' if col != '结果' else f'color: {row["_pass_color"]}; font-weight: bold;'
                for col in df.columns]

    styled_df = df.drop(columns=['id', '_pass_color']).style.apply(style_result, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    stats = calculate_parallel_stats()
    st.caption(f"总计: {stats['total']} 条 | 合格: {stats['passed']} | "
               f"不合格: {stats['failed']} | 合格率: {stats['pass_rate']:.1f}%")


def _render_parallel_new():
    st.subheader("➕ 新增平行样对比")

    all_samples = get_all_samples()

    with st.form("new_parallel_form"):
        col1, col2 = st.columns(2)
        with col1:
            sample_options = {f"{s['sample_no']} - {s['sampling_site']}": s['id']
                             for s in all_samples}
            parent_select = st.selectbox(
                "原始样本 *",
                list(sample_options.keys()),
                key="pl_parent_select",
            )
            parent_id = sample_options[parent_select]
            parent_no = parent_select.split(' - ')[0]

            parallel_type = st.selectbox(
                "对比类型 *",
                ["duplicate", "parallel", "blank", "standard"],
                format_func=lambda x: get_parallel_type_name(x),
                key="pl_type_select",
            )

            parameter = st.selectbox(
                "对比参数 *",
                ["D50", "D10", "D25", "D75", "D90", "回收率", "分选系数"],
                key="pl_param_select",
            )

            tolerance = st.number_input(
                "允许相对偏差(%) *",
                min_value=0.01,
                max_value=100.0,
                value=5.0,
                step=0.1,
                key="pl_tolerance",
            )

        with col2:
            has_parallel_sample = st.checkbox("关联对比样本", value=True)
            if has_parallel_sample:
                parallel_select = st.selectbox(
                    "对比样本",
                    list(sample_options.keys()),
                    key="pl_parallel_select",
                )
                parallel_id = sample_options[parallel_select]
                parallel_no = parallel_select.split(' - ')[0]
            else:
                parallel_id = None
                parallel_no = None

            comparison_date = st.date_input("对比日期", value=datetime.now().date())
            operator = st.text_input("操作员")

        st.markdown("---")
        st.markdown("**测量值**")
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            original_value = st.number_input(
                "原始值 *",
                min_value=0.0,
                step=0.001,
                format="%.4f",
                key="pl_orig_val",
            )
        with col_v2:
            parallel_value = st.number_input(
                "对比值 *",
                min_value=0.0,
                step=0.001,
                format="%.4f",
                key="pl_para_val",
            )

        remarks = st.text_area("备注", height=60, key="pl_remarks")

        if st.form_submit_button("保存对比记录", type="primary"):
            if original_value <= 0 and parallel_value <= 0:
                st.error("请至少填写一个测量值")
            else:
                from analysis import calculate_analysis
                ps_id = add_parallel_sample(
                    parent_sample_id=parent_id,
                    parent_sample_no=parent_no,
                    parallel_sample_id=parallel_id,
                    parallel_sample_no=parallel_no,
                    parallel_type=parallel_type,
                    parameter=parameter,
                    original_value=original_value if original_value > 0 else None,
                    parallel_value=parallel_value if parallel_value > 0 else None,
                    tolerance_pct=tolerance,
                    comparison_date=comparison_date.strftime('%Y-%m-%d'),
                    operator=operator.strip() if operator.strip() else None,
                    remarks=remarks.strip() if remarks.strip() else None,
                )
                st.success("对比记录已保存！")
                st.rerun()


def _render_parallel_stats():
    st.subheader("📊 质量统计")

    col1, col2 = st.columns(2)
    with col1:
        date_range = st.selectbox(
            "统计周期",
            ["近7天", "近30天", "近90天", "全部"],
            index=1,
            key="pl_stats_range",
        )
    with col2:
        stat_type = st.selectbox(
            "对比类型",
            ["全部", "duplicate", "parallel", "blank", "standard"],
            format_func=lambda x: "全部" if x == "全部" else get_parallel_type_name(x),
            index=0,
            key="pl_stats_type",
        )

    today = datetime.now().date()
    if date_range == "近7天":
        date_from = (today - timedelta(days=7)).strftime('%Y-%m-%d')
    elif date_range == "近30天":
        date_from = (today - timedelta(days=30)).strftime('%Y-%m-%d')
    elif date_range == "近90天":
        date_from = (today - timedelta(days=90)).strftime('%Y-%m-%d')
    else:
        date_from = None

    stats = calculate_parallel_stats(
        parallel_type=stat_type if stat_type != "全部" else None,
        date_from=date_from,
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总检测数", stats['total'])
    with col2:
        st.metric("合格数", stats['passed'])
    with col3:
        st.metric("不合格数", stats['failed'])
    with col4:
        st.metric("合格率", f"{stats['pass_rate']:.1f}%")

    st.markdown("---")

    records = get_parallel_samples(
        parallel_type=stat_type if stat_type != "全部" else None,
        date_from=date_from,
    )

    if records:
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['comparison_date']).dt.date

        daily = df.groupby('date').agg(
            总次数=('id', 'count'),
            合格数=('is_pass', 'sum'),
        ).reset_index()
        daily['合格率(%)'] = daily['合格数'] / daily['总次数'] * 100

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=("每日检测数量", "每日合格率趋势"),
        )

        fig.add_trace(
            go.Bar(x=daily['date'], y=daily['总次数'], name='总次数',
                   marker_color='#1f77b4'),
            row=1, col=1
        )
        fig.add_trace(
            go.Bar(x=daily['date'], y=daily['合格数'], name='合格数',
                   marker_color='#2ca02c'),
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(x=daily['date'], y=daily['合格率(%)'],
                       mode='lines+markers', name='合格率',
                       line=dict(color='#ff7f0e', width=2)),
            row=2, col=1
        )
        fig.add_hline(y=95, line_dash="dash", line_color="red",
                      annotation_text="目标线 95%", row=2, col=1)

        fig.update_yaxes(title_text="次数", row=1, col=1)
        fig.update_yaxes(title_text="合格率(%)", range=[0, 105], row=2, col=1)
        fig.update_layout(height=500, showlegend=False)

        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### 按参数统计")
        param_stats = df.groupby('parameter').agg(
            总次数=('id', 'count'),
            合格数=('is_pass', 'sum'),
            平均偏差=('relative_deviation', 'mean'),
        ).reset_index()
        param_stats['合格率(%)'] = param_stats['合格数'] / param_stats['总次数'] * 100
        param_stats['平均偏差(%)'] = param_stats['平均偏差'].round(2)

        st.dataframe(param_stats[['parameter', '总次数', '合格数', '合格率(%)', '平均偏差(%)']],
                     use_container_width=True, hide_index=True)
    else:
        st.info("暂无统计数据")


def render_qc_alerts():
    st.header("🔔 质量预警")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        level_filter = st.selectbox(
            "预警级别",
            ["全部", "error", "warning", "info"],
            format_func=lambda x: "全部" if x == "全部" else get_alert_level_name(x),
            index=0,
        )
    with col_f2:
        ack_filter = st.selectbox(
            "处理状态",
            ["未确认", "已确认", "全部"],
            index=0,
        )
    with col_f3:
        type_filter = st.selectbox(
            "预警类型",
            ["全部", "recovery_abnormal", "parallel_failed", "calibration_due",
             "instrument_error", "data_outlier"],
            format_func=lambda x: {
                "全部": "全部",
                "recovery_abnormal": "回收率异常",
                "parallel_failed": "平行样不合格",
                "calibration_due": "校准到期",
                "instrument_error": "仪器故障",
                "data_outlier": "数据离群",
            }.get(x, x),
            index=0,
        )

    ack_value = None
    if ack_filter == "未确认":
        ack_value = False
    elif ack_filter == "已确认":
        ack_value = True

    alerts = get_alerts(
        alert_level=level_filter if level_filter != "全部" else None,
        alert_type=type_filter if type_filter != "全部" else None,
        acknowledged=ack_value,
        limit=200,
    )

    if not alerts:
        st.info("暂无预警记录")
        return

    summary = get_alert_summary()
    unack_count = summary.get('unacknowledged_count', 0)
    if unack_count > 0:
        st.warning(f"⏳ 有 {unack_count} 条预警待确认")

    display_data = []
    for a in alerts:
        level_icon = {'error': '🔴', 'warning': '🟡', 'info': '🔵'}.get(a['alert_level'], '⚪')
        ack_status = '✅' if a['is_acknowledged'] else '⏳'

        display_data.append({
            '状态': ack_status,
            '级别': f"{level_icon} {get_alert_level_name(a['alert_level'])}",
            '_level_code': a['alert_level'],
            '类型': {
                'recovery_abnormal': '回收率异常',
                'parallel_failed': '平行样不合格',
                'calibration_due': '校准到期',
                'instrument_error': '仪器故障',
                'data_outlier': '数据离群',
                'other': '其他',
            }.get(a.get('alert_type', ''), a.get('alert_type', '')),
            '标题': a.get('title', ''),
            '关联对象': a.get('related_entity_name') or '—',
            '参数': a.get('parameter') or '—',
            '实际值': f"{a['actual_value']:.2f}" if a.get('actual_value') is not None else '—',
            '期望值': f"{a['expected_value']:.2f}" if a.get('expected_value') is not None else '—',
            '创建时间': a.get('created_at', '')[:19] if a.get('created_at') else '',
            'id': a['id'],
        })

    df = pd.DataFrame(display_data)

    def style_level(row):
        color_map = {
            'error': 'color: red; font-weight: bold;',
            'warning': 'color: orange; font-weight: bold;',
            'info': 'color: blue; font-weight: bold;',
        }
        return ['' if col != '级别' else color_map.get(row['_level_code'], '')
                for col in df.columns]

    styled_df = df.drop(columns=['id', '_level_code']).style.apply(style_level, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("⚙️ 批量操作")

    unack_alerts = [a for a in alerts if not a['is_acknowledged']]
    if unack_alerts:
        alert_options = {f"[{get_alert_level_name(a['alert_level'])}] {a['title']}": a['id']
                        for a in unack_alerts}
        selected = st.multiselect("选择要确认的预警", list(alert_options.keys()))

        col1, col2 = st.columns([2, 1])
        with col1:
            ack_remark = st.text_input("确认备注", placeholder="可选：填写确认说明")
        with col2:
            st.text("")
            if st.button("确认选中预警", type="primary", use_container_width=True):
                if selected:
                    for sel in selected:
                        aid = alert_options[sel]
                        acknowledge_alert(aid, remarks=ack_remark.strip() or None)
                    st.success(f"已确认 {len(selected)} 条预警")
                    st.rerun()
                else:
                    st.warning("请先选择预警")
    else:
        st.success("✅ 所有预警均已确认处理")


def render_retest_requests():
    st.header("🔄 复测申请管理")

    tab1, tab2, tab3 = st.tabs(["申请列表", "新建申请", "申请统计"])

    with tab1:
        _render_retest_list()

    with tab2:
        _render_retest_new()

    with tab3:
        _render_retest_stats()


def _render_retest_list():
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filter = st.selectbox(
            "状态筛选",
            ["全部", "pending", "approved", "rejected", "completed"],
            format_func=lambda x: "全部" if x == "全部" else get_retest_status_name(x),
            index=0,
            key="rt_status_filter",
        )
    with col_f2:
        type_filter = st.selectbox(
            "类型筛选",
            ["全部", "abnormal", "quality", "customer", "other"],
            format_func=lambda x: {
                "全部": "全部",
                "abnormal": "结果异常",
                "quality": "质量问题",
                "customer": "客户要求",
                "other": "其他原因",
            }.get(x, x),
            index=0,
            key="rt_type_filter",
        )

    requests = get_retest_requests(
        status=status_filter if status_filter != "全部" else None,
    )

    if type_filter != "全部":
        requests = [r for r in requests if r.get('request_type') == type_filter]

    if not requests:
        st.info("暂无复测申请")
        return

    display_data = []
    for r in requests:
        status_name = get_retest_status_name(r.get('status', ''))
        status_color = {
            'pending': 'orange',
            'approved': 'blue',
            'rejected': 'red',
            'completed': 'green',
        }.get(r.get('status', ''), 'gray')

        display_data.append({
            '申请编号': r.get('request_no', ''),
            '样本编号': r.get('sample_no', ''),
            '类型': {
                'abnormal': '结果异常',
                'quality': '质量问题',
                'customer': '客户要求',
                'other': '其他原因',
            }.get(r.get('request_type', ''), r.get('request_type', '')),
            '申请原因': r.get('reason', '')[:30] + '...' if len(str(r.get('reason', ''))) > 30 else r.get('reason', ''),
            '申请人': r.get('requested_by') or '—',
            '申请时间': r.get('requested_at', '')[:19] if r.get('requested_at') else '',
            '状态': status_name,
            '_status_color': status_color,
            '审批人': r.get('approver') or '—',
            'id': r['id'],
        })

    df = pd.DataFrame(display_data)

    def style_status(row):
        return ['' if col != '状态' else f'color: {row["_status_color"]}; font-weight: bold;'
                for col in df.columns]

    styled_df = df.drop(columns=['id', '_status_color']).style.apply(style_status, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📋 申请详情与审批")

    retest_options = {f"{r['request_no']} - {r['sample_no']}": r['id'] for r in requests}
    if retest_options:
        selected = st.selectbox("选择申请查看详情", list(retest_options.keys()),
                               key="rt_detail_select")
        selected_id = retest_options[selected]

        request_data = None
        for r in requests:
            if r['id'] == selected_id:
                request_data = r
                break

        if request_data:
            with st.expander("📝 申请详情", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"申请编号: {request_data.get('request_no', '')}")
                    st.caption(f"样本编号: {request_data.get('sample_no', '')}")
                    st.caption(f"申请类型: {request_data.get('request_type', '')}")
                    st.caption(f"申请人: {request_data.get('requested_by') or '—'}")
                with col2:
                    st.caption(f"申请时间: {request_data.get('requested_at', '')[:19]}")
                    st.caption(f"当前状态: {get_retest_status_name(request_data.get('status', ''))}")
                    st.caption(f"审批人: {request_data.get('approver') or '—'}")
                    if request_data.get('approved_at'):
                        st.caption(f"审批时间: {request_data['approved_at'][:19]}")

                st.markdown("**申请原因：**")
                st.write(request_data.get('reason', ''))

                if request_data.get('approval_comment'):
                    st.markdown("**审批意见：**")
                    st.write(request_data['approval_comment'])

                if request_data.get('retest_result'):
                    st.markdown("**复测结果：**")
                    st.write(request_data['retest_result'])

                if request_data.get('remarks'):
                    st.markdown("**备注：**")
                    st.write(request_data['remarks'])

            if request_data.get('status') == 'pending':
                st.markdown("---")
                col1, col2 = st.columns([1, 1])
                with col1:
                    approve_comment = st.text_area("审批意见", height=80, key="rt_approve_comment")
                with col2:
                    st.text("")
                    st.text("")
                    if st.button("✅ 批准申请", type="primary", use_container_width=True):
                        approve_retest(selected_id, comment=approve_comment.strip())
                        st.success("已批准复测申请")
                        st.rerun()
                    if st.button("❌ 拒绝申请", type="secondary", use_container_width=True):
                        reject_retest(selected_id, comment=approve_comment.strip())
                        st.warning("已拒绝复测申请")
                        st.rerun()

            elif request_data.get('status') == 'approved':
                st.markdown("---")
                with st.expander("📝 填写复测结果", expanded=False):
                    with st.form("rt_complete_form"):
                        retest_result = st.text_area("复测结果说明", height=100)
                        remarks = st.text_area("备注", height=60)
                        if st.form_submit_button("标记为已完成", type="primary"):
                            complete_retest(selected_id, retest_result=retest_result.strip(),
                                          remarks=remarks.strip() if remarks.strip() else None)
                            st.success("复测已完成")
                            st.rerun()


def _render_retest_new():
    st.subheader("➕ 新建复测申请")

    all_samples = get_all_samples()

    with st.form("new_retest_form"):
        col1, col2 = st.columns(2)
        with col1:
            sample_options = {f"{s['sample_no']} - {s['sampling_site']}": s['id']
                             for s in all_samples}
            sample_select = st.selectbox("选择样本 *", list(sample_options.keys()))
            sample_id = sample_options[sample_select]
            sample_no = sample_select.split(' - ')[0]

            request_type = st.selectbox(
                "申请类型 *",
                ["abnormal", "quality", "customer", "other"],
                format_func=lambda x: {
                    'abnormal': '结果异常',
                    'quality': '质量问题',
                    'customer': '客户要求',
                    'other': '其他原因',
                }.get(x, x),
            )

            requested_by = st.text_input("申请人")

        with col2:
            st.caption("请填写复测申请原因，越详细越好")
            reason = st.text_area("申请原因 *", height=200,
                                 placeholder="请详细说明需要复测的原因，如：数据异常、与历史数据偏差大、平行样不合格等")

            remarks = st.text_area("备注", height=80)

        if st.form_submit_button("提交申请", type="primary"):
            if not reason.strip():
                st.error("请填写申请原因")
            else:
                req_id, req_no = create_retest_request(
                    sample_id=sample_id,
                    sample_no=sample_no,
                    request_type=request_type,
                    reason=reason.strip(),
                    requested_by=requested_by.strip() if requested_by.strip() else None,
                    remarks=remarks.strip() if remarks.strip() else None,
                )
                st.success(f"复测申请已提交！申请编号: {req_no}")
                st.rerun()


def _render_retest_stats():
    st.subheader("📊 复测统计")

    all_requests = get_retest_requests()

    if not all_requests:
        st.info("暂无复测申请数据")
        return

    df = pd.DataFrame(all_requests)

    status_counts = df['status'].value_counts()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总申请数", len(df))
    with col2:
        st.metric("待审批", status_counts.get('pending', 0))
    with col3:
        st.metric("已批准", status_counts.get('approved', 0))
    with col4:
        st.metric("已完成", status_counts.get('completed', 0))

    st.markdown("---")

    fig = go.Figure(data=[
        go.Pie(
            labels=[get_retest_status_name(s) for s in status_counts.index],
            values=status_counts.values,
            hole=0.5,
            marker_colors=['orange', 'blue', 'red', 'green', 'gray'],
        )
    ])
    fig.update_layout(title="复测申请状态分布", height=400)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("#### 按原因类型统计")

    type_counts = df['request_type'].value_counts()
    type_labels = {
        'abnormal': '结果异常',
        'quality': '质量问题',
        'customer': '客户要求',
        'other': '其他原因',
    }

    fig2 = go.Figure(data=[
        go.Bar(
            x=[type_labels.get(t, t) for t in type_counts.index],
            y=type_counts.values,
            marker_color='#ff7f0e',
        )
    ])
    fig2.update_layout(title="复测申请原因分布", height=400, yaxis_title="数量")
    st.plotly_chart(fig2, use_container_width=True)


def render_qc_report():
    st.header("📄 质量报告")

    tab1, tab2 = st.tabs(["质量汇总报告", "导出设置"])

    with tab1:
        _render_qc_report_summary()

    with tab2:
        _render_qc_report_settings()


def _render_qc_report_summary():
    st.subheader("📊 质量汇总报告")

    col1, col2 = st.columns(2)
    with col1:
        report_start = st.date_input("报告开始日期",
                                 value=datetime.now().date() - timedelta(days=30))
    with col2:
        report_end = st.date_input("报告结束日期", value=datetime.now().date())

    date_from = report_start.strftime('%Y-%m-%d')
    date_to = report_end.strftime('%Y-%m-%d')

    stats = get_qc_dashboard_stats(date_from=date_from, date_to=date_to)

    st.markdown("---")
    st.markdown("### 📈 总体指标概览")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("实验批次", stats['batches']['total'])
    with col2:
        st.metric("平行样检测数", stats['parallel_qc']['total'])
    with col3:
        pass_rate = f"{stats['parallel_qc']['pass_rate']:.1f}%"
        st.metric("合格率", pass_rate)
    with col4:
        st.metric("质量预警数", stats['alerts'].get('unacknowledged_count', 0))

    st.markdown("---")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("#### 📦 批次统计")
        batch_data = {
            '状态': ['计划中', '进行中', '已完成', '已取消'],
            '数量': [
                stats['batches'].get('planning', 0),
                stats['batches'].get('in_progress', 0),
                stats['batches'].get('completed', 0),
                stats['batches'].get('cancelled', 0),
            ]
        }
        st.dataframe(pd.DataFrame(batch_data), use_container_width=True, hide_index=True)

    with col_right:
        st.markdown("#### 🔬 仪器状态")
        inst = stats['instruments']
        inst_data = {
            '项目': ['总台数', '在用', '校准即将到期(30天内)', '校准已超期'],
            '数量': [
                inst['total'],
                inst['active'],
                inst['calibration_due'],
                inst['overdue'],
            ]
        }
        st.dataframe(pd.DataFrame(inst_data), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### ⚖️ 平行样质量趋势")

    parallel_records = get_parallel_samples(date_from=date_from, date_to=date_to)
    if parallel_records:
        df = pd.DataFrame(parallel_records)
        df['date'] = pd.to_datetime(df['comparison_date']).dt.date

        daily = df.groupby('date').agg(
            总次数=('id', 'count'),
            合格数=('is_pass', 'sum'),
        ).reset_index()
        daily['合格率(%)'] = daily['合格数'] / daily['总次数'] * 100

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=("检测数量", "合格率趋势"),
        )

        fig.add_trace(
            go.Bar(x=daily['date'], y=daily['总次数'], name='总次数',
                   marker_color='#1f77b4'),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=daily['date'], y=daily['合格率(%)'],
                       mode='lines+markers', name='合格率',
                       line=dict(color='#ff7f0e', width=2)),
            row=2, col=1
        )
        fig.add_hline(y=95, line_dash="dash", line_color="red",
                      annotation_text="目标 95%", row=2, col=1)
        fig.update_yaxes(title_text="次数", row=1, col=1)
        fig.update_yaxes(title_text="合格率(%)", range=[0, 105], row=2, col=1)
        fig.update_layout(height=450, showlegend=False)

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("该时间段内暂无平行样检测数据")

    st.markdown("---")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("📄 导出 CSV 报告", type="primary", use_container_width=True):
            csv_data = _generate_qc_csv_report(date_from, date_to, stats)
            st.download_button(
                "下载 CSV 报告",
                data=csv_data.encode('utf-8-sig'),
                file_name=f"质量报告_{date_from}_{date_to}.csv",
                mime='text/csv',
                use_container_width=True,
            )

    with col2:
        try:
            from report import generate_pdf_report
            pdf_available = True
        except ImportError:
            pdf_available = False

        if st.button("📕 导出 PDF 报告", disabled=not pdf_available, use_container_width=True):
            st.info("PDF 报告生成功能开发中...")

    with col3:
        try:
            from report import generate_word_report
            word_available = True
        except ImportError:
            word_available = False

        if st.button("📘 导出 Word 报告", disabled=not word_available, use_container_width=True):
            st.info("Word 报告生成功能开发中...")


def _generate_qc_csv_report(date_from, date_to, stats):
    lines = []
    lines.append("火山灰实验室质量控制报告")
    lines.append(f"统计周期: {date_from} 至 {date_to}")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    lines.append("一、总体指标")
    lines.append(f"实验批次总数: {stats['batches']['total']}")
    lines.append(f"进行中批次: {stats['batches'].get('in_progress', 0)}")
    lines.append(f"已完成批次: {stats['batches'].get('completed', 0)}")
    lines.append(f"平行样检测总数: {stats['parallel_qc']['total']}")
    lines.append(f"合格数: {stats['parallel_qc']['passed']}")
    lines.append(f"不合格数: {stats['parallel_qc']['failed']}")
    lines.append(f"合格率: {stats['parallel_qc']['pass_rate']:.1f}%")
    lines.append(f"平均相对偏差: {stats['parallel_qc']['avg_deviation']:.2f}%")
    lines.append("")

    lines.append("二、仪器状态")
    inst = stats['instruments']
    lines.append(f"仪器总数: {inst['total']}")
    lines.append(f"在用仪器: {inst['active']}")
    lines.append(f"校准即将到期(30天内): {inst['calibration_due']}")
    lines.append(f"校准已超期: {inst['overdue']}")
    lines.append("")

    lines.append("三、质量预警")
    alerts = stats['alerts']
    lines.append(f"未处理预警数: {alerts.get('unacknowledged_count', 0)}")
    by_level = alerts.get('by_level_unack', {})
    lines.append(f"  严重: {by_level.get('error', 0)}")
    lines.append(f"  警告: {by_level.get('warning', 0)}")
    lines.append(f"  提示: {by_level.get('info', 0)}")
    lines.append("")

    lines.append("四、复测申请")
    retests = stats['retests']
    lines.append(f"待审批: {retests.get('pending', 0)}")
    lines.append(f"总申请数: {retests.get('total', 0)}")
    lines.append("")

    lines.append("五、平行样详细记录")
    parallel_records = get_parallel_samples(date_from=date_from, date_to=date_to)
    if parallel_records:
        lines.append("对比日期,类型,参数,原始样本,对比样本,原始值,对比值,相对偏差(%),允许偏差(%),结果")
        for r in parallel_records:
            is_pass = "合格" if r.get('is_pass') == 1 else "不合格"
            lines.append(
                f"{r.get('comparison_date', '')},"
                f"{get_parallel_type_name(r.get('parallel_type', ''))},"
                f"{r.get('parameter', '')},"
                f"{r.get('parent_sample_no', '')},"
                f"{r.get('parallel_sample_no', '')},"
                f"{r.get('original_value', '')},"
                f"{r.get('parallel_value', '')},"
                f"{r.get('relative_deviation', '')},"
                f"{r.get('tolerance_pct', '')},"
                f"{is_pass}"
            )
    else:
        lines.append("暂无数据")

    return '\n'.join(lines)


def _render_qc_report_settings():
    st.subheader("⚙️ 报告设置")

    standards = get_qc_standards()

    st.markdown("#### 质量控制标准")
    if standards:
        display_data = []
        for std in standards:
            display_data.append({
                '标准编号': std.get('standard_code', ''),
                '标准名称': std.get('standard_name', ''),
                '参数': std.get('parameter_name', ''),
                '单位': std.get('unit', ''),
                '目标值': std.get('target_value') or '—',
                '正偏差': std.get('tolerance_plus') or '—',
                '负偏差': std.get('tolerance_minus') or '—',
                '方法': std.get('method') or '—',
            })
        st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
    else:
        st.info("暂无质量控制标准")

    st.markdown("---")
    st.info("💡 提示：更多报告模板和配置功能正在开发中...")
