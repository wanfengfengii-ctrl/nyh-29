import streamlit as st
import pandas as pd
from typing import List, Dict, Optional, Tuple, Any, Callable
from dataclasses import dataclass


@dataclass
class StatusColor:
    SUCCESS = "green"
    WARNING = "orange"
    ERROR = "red"
    INFO = "blue"
    PENDING = "orange"
    IN_PROGRESS = "#1890ff"
    COMPLETED = "green"
    RETURNED = "red"
    OVERDUE = "red"
    NONE = "gray"


@dataclass
class PriorityColor:
    HIGH = "red"
    NORMAL = "orange"
    LOW = "green"
    NONE = "gray"


def render_page_header(title: str, subtitle: Optional[str] = None, 
                       back_button: Optional[Tuple[str, str]] = None) -> None:
    if back_button:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.header(title)
            if subtitle:
                st.caption(subtitle)
        with col2:
            if st.button(back_button[0], use_container_width=True):
                from .router import navigate_to
                navigate_to(back_button[1])
    else:
        st.header(title)
        if subtitle:
            st.caption(subtitle)
    st.markdown("---")


def render_metric_card(label: str, value: Any, delta: Optional[Any] = None,
                       delta_color: str = "normal") -> None:
    st.metric(label, value, delta=delta, delta_color=delta_color)


def render_metrics_row(metrics: List[Dict[str, Any]]) -> None:
    cols = st.columns(len(metrics))
    for i, metric in enumerate(metrics):
        with cols[i]:
            st.metric(
                label=metric.get("label", ""),
                value=metric.get("value", ""),
                delta=metric.get("delta"),
                delta_color=metric.get("delta_color", "normal")
            )


def render_data_table(
    df: pd.DataFrame,
    style_config: Optional[Dict[str, Any]] = None,
    hide_index: bool = True,
    use_container_width: bool = True,
    height: Optional[int] = None,
    status_column: Optional[str] = None,
    status_color_map: Optional[Dict[str, str]] = None,
    highlight_rows: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if df.empty:
        render_empty_state("暂无数据")
        return

    styled_df = df.copy()
    hidden_cols = []

    if status_column and status_color_map:
        def _style_status(row):
            styles = []
            status_val = row.get(status_column, "")
            for col in row.index:
                style = ""
                if col == status_column:
                    color = status_color_map.get(status_val, "gray")
                    style += f"color: {color}; font-weight: bold; "
                styles.append(style)
            return styles
        
        styled_df = styled_df.style.apply(_style_status, axis=1)

    if highlight_rows:
        if not hasattr(styled_df, 'apply') or not callable(getattr(styled_df, 'apply')):
            styled_df = styled_df.style
        
        def _highlight_row(row):
            styles = [''] * len(row)
            for hr in highlight_rows:
                condition = hr.get("condition", lambda r: False)
                if condition(row):
                    bg_color = hr.get("background_color", "#fff1f0")
                    styles = [f"background-color: {bg_color}; " for _ in row.index]
                    break
            return styles
        
        styled_df = styled_df.apply(_highlight_row, axis=1)

    if style_config and style_config.get("hidden_columns"):
        hidden_cols = style_config["hidden_columns"]
        if hasattr(styled_df, 'hide'):
            styled_df = styled_df.hide(axis="columns", subset=hidden_cols)

    kwargs = {
        "use_container_width": use_container_width,
        "hide_index": hide_index,
    }
    if height:
        kwargs["height"] = height

    st.dataframe(styled_df, **kwargs)


def render_filter_bar(filters: List[Dict[str, Any]]) -> Dict[str, Any]:
    result = {}
    cols = st.columns(len(filters))
    
    for i, filt in enumerate(filters):
        with cols[i]:
            filter_type = filt.get("type", "text")
            key = filt.get("key", f"filter_{i}")
            label = filt.get("label", "")
            
            if filter_type == "text":
                result[key] = st.text_input(label, value=filt.get("default", ""))
            elif filter_type == "select":
                options = filt.get("options", [])
                format_func = filt.get("format_func")
                index = filt.get("index", 0)
                if format_func:
                    result[key] = st.selectbox(
                        label, options, index=index,
                        format_func=format_func
                    )
                else:
                    result[key] = st.selectbox(label, options, index=index)
            elif filter_type == "date":
                result[key] = st.date_input(label, value=filt.get("default"))
            elif filter_type == "multiselect":
                options = filt.get("options", [])
                result[key] = st.multiselect(label, options, default=filt.get("default", []))
    
    return result


def render_status_badge(text: str, color: str = "gray") -> str:
    return f"<span style='color: {color}; font-weight: bold;'>● {text}</span>"


def render_empty_state(message: str, icon: str = "📭") -> None:
    st.info(f"{icon} {message}")


def render_confirm_dialog(
    state_key: str,
    message: str,
    confirm_label: str = "确认",
    cancel_label: str = "取消",
    confirm_type: str = "primary",
) -> Tuple[bool, bool]:
    confirmed = False
    cancelled = False

    if st.session_state.get(state_key):
        st.warning(f"⚠️ {message}")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button(confirm_label, type=confirm_type, use_container_width=True):
                confirmed = True
                st.session_state[state_key] = False
        with col_no:
            if st.button(cancel_label, use_container_width=True):
                cancelled = True
                st.session_state[state_key] = False

    return confirmed, cancelled


def render_action_bar(
    items: List[Dict[str, Any]],
    select_options: Optional[List[Tuple[str, Any]]] = None,
    select_label: str = "选择",
) -> Dict[str, Any]:
    result = {"selected": None, "actions": {}}

    if select_options:
        col_select, *col_actions = st.columns([3] + [1] * len(items))
        with col_select:
            options = [opt[0] for opt in select_options]
            values = [opt[1] for opt in select_options]
            selected_label = st.selectbox(
                select_label, options, label_visibility="collapsed"
            )
            idx = options.index(selected_label)
            result["selected"] = values[idx]
    else:
        col_actions = st.columns(len(items))

    for i, item in enumerate(items):
        with col_actions[i]:
            key = item.get("key", f"action_{i}")
            label = item.get("label", "")
            btn_type = item.get("type", "secondary")
            disabled = item.get("disabled", False)
            
            result["actions"][key] = st.button(
                label, type=btn_type, use_container_width=True, disabled=disabled
            )

    return result


def render_section_header(title: str, expanded: bool = True) -> bool:
    with st.expander(title, expanded=expanded):
        return True


def render_divider() -> None:
    st.markdown("---")
