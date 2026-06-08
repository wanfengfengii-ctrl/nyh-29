from qc_pages import (
    render_qc_dashboard as _render_qc_dashboard,
    render_batch_management as _render_batch_management,
    render_instrument_management as _render_instrument_management,
    render_parallel_qc as _render_parallel_qc,
    render_qc_alerts as _render_qc_alerts,
    render_retest_requests as _render_retest_requests,
    render_qc_report as _render_qc_report,
)


def render_qc_dashboard():
    _render_qc_dashboard()


def render_batch_management():
    _render_batch_management()


def render_instrument_management():
    _render_instrument_management()


def render_parallel_qc():
    _render_parallel_qc()


def render_qc_alerts():
    _render_qc_alerts()


def render_retest_requests():
    _render_retest_requests()


def render_qc_report():
    _render_qc_report()
