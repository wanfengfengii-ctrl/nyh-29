import streamlit as st
from typing import Dict, Callable, Optional


class Router:
    def __init__(self):
        self._routes: Dict[str, Callable] = {}
        self._current_page_key = "current_page"
        self._default_page = "home"

    def register(self, page_name: str, render_func: Callable) -> None:
        self._routes[page_name] = render_func

    def register_batch(self, routes: Dict[str, Callable]) -> None:
        for page_name, render_func in routes.items():
            self.register(page_name, render_func)

    def navigate(self, page_name: str, **kwargs) -> None:
        if page_name not in self._routes:
            raise ValueError(f"Page '{page_name}' is not registered")
        st.session_state[self._current_page_key] = page_name
        for key, value in kwargs.items():
            st.session_state[key] = value
        st.rerun()

    def get_current_page(self) -> str:
        return st.session_state.get(self._current_page_key, self._default_page)

    def render(self) -> None:
        current_page = self.get_current_page()
        render_func = self._routes.get(current_page)
        if render_func:
            render_func()
        else:
            render_func = self._routes.get(self._default_page)
            if render_func:
                render_func()
            else:
                st.error(f"页面 '{current_page}' 不存在")


def navigate_to(page: str, **kwargs) -> None:
    st.session_state.current_page = page
    for key, value in kwargs.items():
        st.session_state[key] = value
    if "confirm_delete_id" in st.session_state:
        st.session_state.confirm_delete_id = None
    if "batch_delete_ids" in st.session_state:
        st.session_state.batch_delete_ids = []
    st.rerun()


def get_current_page() -> str:
    return st.session_state.get("current_page", "样本列表")
