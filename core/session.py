import streamlit as st
from typing import Any, Dict, Optional


def init_session_state(defaults: Optional[Dict[str, Any]] = None) -> None:
    if defaults:
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value


def get_state(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def set_state(key: str, value: Any) -> None:
    st.session_state[key] = value


def set_states(**kwargs) -> None:
    for key, value in kwargs.items():
        st.session_state[key] = value


def has_state(key: str) -> bool:
    return key in st.session_state


def clear_state(*keys: str) -> None:
    for key in keys:
        if key in st.session_state:
            del st.session_state[key]
