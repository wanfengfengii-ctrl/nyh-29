import streamlit as st
import pandas as pd

from core import render_page_header, render_empty_state
from db import get_operation_logs


def render_operation_logs():
    render_page_header("📄 操作日志")
    
    logs = get_operation_logs(limit=200)
    
    if not logs:
        render_empty_state("暂无操作日志")
        return
    
    log_df = pd.DataFrame(logs)
    
    display_df = log_df[['created_at', 'operation_type', 'entity_type', 'entity_name', 'details', 'operator']].copy()
    display_df.columns = ['时间', '操作类型', '对象类型', '对象名称', '详情', '操作人']
    
    type_map = {
        'create': '创建',
        'update': '更新',
        'delete': '删除',
        'batch_delete': '批量删除',
        'update_sieve': '更新筛分数据',
        'batch_import': '批量导入',
    }
    display_df['操作类型'] = display_df['操作类型'].map(lambda x: type_map.get(x, x))
    
    entity_map = {
        'sample': '样本',
    }
    display_df['对象类型'] = display_df['对象类型'].map(lambda x: entity_map.get(x, x) if x else '')
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.caption(f"共 {len(logs)} 条操作记录（显示最近 200 条）")
