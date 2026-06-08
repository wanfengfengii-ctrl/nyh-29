import streamlit as st
import traceback
from typing import Any, Callable, Optional, Tuple
from functools import wraps


def handle_error(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = f"操作失败：{str(e)}"
            st.error(error_msg)
            st.caption(f"错误类型: {type(e).__name__}")
            return None
    return wrapper


def safe_operation(
    operation: Callable,
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
    rerun_on_success: bool = False,
) -> Tuple[bool, Any]:
    try:
        result = operation()
        if success_message:
            st.success(success_message)
        if rerun_on_success:
            st.rerun()
        return True, result
    except Exception as e:
        msg = error_message or f"操作失败：{str(e)}"
        st.error(msg)
        return False, str(e)


def safe_db_operation(
    operation: Callable,
    entity_name: str = "数据",
    operation_type: str = "操作",
) -> Tuple[bool, Any]:
    try:
        result = operation()
        return True, result
    except Exception as e:
        error_msg = f"{entity_name}{operation_type}失败：{str(e)}"
        st.error(error_msg)
        return False, str(e)


def show_validation_errors(errors: list) -> None:
    if errors:
        for error in errors:
            st.error(error)


def show_success_message(message: str, icon: str = "✅") -> None:
    st.success(f"{icon} {message}")


def show_warning_message(message: str, icon: str = "⚠️") -> None:
    st.warning(f"{icon} {message}")


def show_error_message(message: str, icon: str = "❌") -> None:
    st.error(f"{icon} {message}")


def show_info_message(message: str, icon: str = "ℹ️") -> None:
    st.info(f"{icon} {message}")


class ErrorBoundary:
    def __init__(self, fallback_message: str = "页面加载出错，请刷新重试"):
        self.fallback_message = fallback_message
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            st.error(self.fallback_message)
            with st.expander("查看详细错误"):
                st.code(traceback.format_exc())
            return True
        return False
