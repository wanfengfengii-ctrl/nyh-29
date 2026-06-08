import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "volcanic_ash.db")

WORKFLOW_STAGES = [
    {"code": "registration", "name": "样本登记", "order": 1, "description": "样本信息登记与初审"},
    {"code": "sieving", "name": "筛分录入", "order": 2, "description": "实验筛分数据录入"},
    {"code": "review", "name": "结果复核", "order": 3, "description": "实验结果审核与校验"},
    {"code": "report", "name": "报告生成", "order": 4, "description": "分析报告编制与生成"},
    {"code": "archiving", "name": "归档管理", "order": 5, "description": "数据归档与长期保存"},
]

TASK_STATUS = {
    "pending": "待处理",
    "in_progress": "处理中",
    "completed": "已完成",
    "returned": "已退回",
    "overdue": "已超期",
}


@contextmanager
def get_wf_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_workflow_db():
    with get_wf_db() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT DEFAULT 'lab_tech',
                email TEXT,
                phone TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workflow_stages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stage_code TEXT UNIQUE NOT NULL,
                stage_name TEXT NOT NULL,
                stage_order INTEGER NOT NULL,
                description TEXT,
                default_deadline_hours INTEGER DEFAULT 24,
                is_active INTEGER DEFAULT 1
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sample_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER NOT NULL,
                sample_no TEXT NOT NULL,
                current_stage TEXT NOT NULL,
                task_status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'normal',
                assigned_to TEXT,
                deadline TEXT,
                started_at TEXT,
                completed_at TEXT,
                description TEXT,
                created_by TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sample_id) REFERENCES samples (id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_stage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                sample_id INTEGER,
                stage_code TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                operator TEXT,
                assignee TEXT,
                comment TEXT,
                deadline TEXT,
                acted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES sample_tasks (id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                sample_id INTEGER,
                stage_code TEXT NOT NULL,
                approver TEXT NOT NULL,
                approval_result TEXT NOT NULL,
                comment TEXT,
                signed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES sample_tasks (id) ON DELETE CASCADE
            )
        ''')

        _init_default_stages(cursor)
        _init_default_users(cursor)
        _migrate_task_table(cursor)


def _init_default_stages(cursor):
    for stage in WORKFLOW_STAGES:
        cursor.execute('''
            INSERT OR IGNORE INTO workflow_stages 
            (stage_code, stage_name, stage_order, description, default_deadline_hours)
            VALUES (?, ?, ?, ?, ?)
        ''', (stage['code'], stage['name'], stage['order'], stage['description'], 24))


def _init_default_users(cursor):
    default_users = [
        ("admin", "系统管理员", "admin", "admin@lab.com", "13800000000"),
        ("zhang_san", "张三", "lab_tech", "zhangsan@lab.com", "13800000001"),
        ("li_si", "李四", "lab_tech", "lisi@lab.com", "13800000002"),
        ("wang_wu", "王五", "reviewer", "wangwu@lab.com", "13800000003"),
        ("zhao_liu", "赵六", "reviewer", "zhaoliu@lab.com", "13800000004"),
    ]
    for username, full_name, role, email, phone in default_users:
        cursor.execute('''
            INSERT OR IGNORE INTO users (username, full_name, role, email, phone)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, full_name, role, email, phone))


def _migrate_task_table(cursor):
    cursor.execute("PRAGMA table_info(sample_tasks)")
    columns = [row['name'] for row in cursor.fetchall()]

    new_columns = {
        'priority': 'TEXT DEFAULT "normal"',
        'description': 'TEXT',
    }

    for col_name, col_type in new_columns.items():
        if col_name not in columns:
            cursor.execute(f'ALTER TABLE sample_tasks ADD COLUMN {col_name} {col_type}')


def get_all_users(active_only=True):
    with get_wf_db() as conn:
        cursor = conn.cursor()
        if active_only:
            cursor.execute('SELECT * FROM users WHERE is_active = 1 ORDER BY role, full_name')
        else:
            cursor.execute('SELECT * FROM users ORDER BY role, full_name')
        return [dict(row) for row in cursor.fetchall()]


def get_user(username):
    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_stages():
    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM workflow_stages WHERE is_active = 1 ORDER BY stage_order')
        return [dict(row) for row in cursor.fetchall()]


def get_stage_by_code(stage_code):
    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM workflow_stages WHERE stage_code = ?', (stage_code,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_task_for_sample(sample_id, sample_no, created_by='system', description='',
                           priority='normal', deadline_hours=None):
    stages = get_stages()
    if not stages:
        first_stage = 'registration'
    else:
        first_stage = stages[0]['stage_code']

    if deadline_hours is None:
        stage_info = get_stage_by_code(first_stage)
        deadline_hours = stage_info.get('default_deadline_hours', 24) if stage_info else 24

    deadline = (datetime.now() + timedelta(hours=deadline_hours)).strftime('%Y-%m-%d %H:%M:%S')

    with get_wf_db() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO sample_tasks 
            (sample_id, sample_no, current_stage, task_status, priority, 
             deadline, description, created_by)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
        ''', (sample_id, sample_no, first_stage, priority, deadline, description, created_by))

        task_id = cursor.lastrowid

        cursor.execute('''
            INSERT INTO task_stage_logs 
            (task_id, sample_id, stage_code, action, status, operator, comment)
            VALUES (?, ?, ?, 'create', 'pending', ?, '任务创建')
        ''', (task_id, sample_id, first_stage, created_by))

    _log_wf_operation('create_task', 'task', task_id, sample_no,
                      f'为样本 {sample_no} 创建任务', created_by)

    return task_id


def get_task(task_id):
    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sample_tasks WHERE id = ?', (task_id,))
        task = cursor.fetchone()
        if task:
            task = dict(task)
            cursor.execute('''
                SELECT * FROM task_stage_logs 
                WHERE task_id = ? 
                ORDER BY acted_at DESC, id DESC
            ''', (task_id,))
            task['stage_logs'] = [dict(row) for row in cursor.fetchall()]

            cursor.execute('''
                SELECT * FROM approvals 
                WHERE task_id = ? 
                ORDER BY signed_at DESC
            ''', (task_id,))
            task['approvals'] = [dict(row) for row in cursor.fetchall()]

        return task


def get_task_by_sample(sample_id):
    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sample_tasks WHERE sample_id = ? ORDER BY id DESC LIMIT 1',
                       (sample_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_tasks(status=None, stage=None, assignee=None, priority=None,
                  sample_no=None, group_name=None, eruption_layer=None,
                  date_from=None, date_to=None, limit=None, offset=None):
    with get_wf_db() as conn:
        cursor = conn.cursor()

        query = '''
            SELECT t.*, s.sampling_site, s.eruption_layer, s.group_name, s.total_weight
            FROM sample_tasks t
            LEFT JOIN samples s ON t.sample_id = s.id
            WHERE 1=1
        '''
        params = []

        if status:
            query += ' AND t.task_status = ?'
            params.append(status)
        if stage:
            query += ' AND t.current_stage = ?'
            params.append(stage)
        if assignee:
            query += ' AND t.assigned_to = ?'
            params.append(assignee)
        if priority:
            query += ' AND t.priority = ?'
            params.append(priority)
        if sample_no:
            query += ' AND t.sample_no LIKE ?'
            params.append(f'%{sample_no}%')
        if group_name:
            query += ' AND s.group_name = ?'
            params.append(group_name)
        if eruption_layer:
            query += ' AND s.eruption_layer LIKE ?'
            params.append(f'%{eruption_layer}%')
        if date_from:
            query += ' AND t.created_at >= ?'
            params.append(date_from)
        if date_to:
            query += ' AND t.created_at <= ?'
            params.append(date_to)

        query += ' ORDER BY t.priority DESC, t.created_at DESC'

        if limit:
            query += ' LIMIT ?'
            params.append(limit)
        if offset:
            query += ' OFFSET ?'
            params.append(offset)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def assign_task(task_id, assignee, assigner='system', comment='', deadline_hours=None):
    task = get_task(task_id)
    if not task:
        return False

    if deadline_hours:
        deadline = (datetime.now() + timedelta(hours=deadline_hours)).strftime('%Y-%m-%d %H:%M:%S')
    else:
        stage_info = get_stage_by_code(task['current_stage'])
        default_hours = stage_info.get('default_deadline_hours', 24) if stage_info else 24
        deadline = (datetime.now() + timedelta(hours=default_hours)).strftime('%Y-%m-%d %H:%M:%S')

    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE sample_tasks 
            SET assigned_to = ?, deadline = ?, task_status = 'pending',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (assignee, deadline, task_id))

        cursor.execute('''
            INSERT INTO task_stage_logs 
            (task_id, sample_id, stage_code, action, status, operator, assignee, comment)
            VALUES (?, ?, ?, 'assign', 'pending', ?, ?, ?)
        ''', (task_id, task['sample_id'], task['current_stage'], assigner, assignee, comment))

    _log_wf_operation('assign_task', 'task', task_id, task['sample_no'],
                      f'将任务分派给 {assignee}', assigner)

    return True


def start_task(task_id, operator, comment=''):
    task = get_task(task_id)
    if not task:
        return False

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE sample_tasks 
            SET task_status = 'in_progress', started_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (now, task_id))

        cursor.execute('''
            INSERT INTO task_stage_logs 
            (task_id, sample_id, stage_code, action, status, operator, comment)
            VALUES (?, ?, ?, 'start', 'in_progress', ?, ?)
        ''', (task_id, task['sample_id'], task['current_stage'], operator, comment))

    _log_wf_operation('start_task', 'task', task_id, task['sample_no'],
                      f'开始处理任务 - {task["current_stage"]}', operator)

    return True


def complete_stage(task_id, operator, comment=''):
    task = get_task(task_id)
    if not task:
        return False

    current_stage = task['current_stage']
    stages = get_stages()
    stage_codes = [s['stage_code'] for s in stages]

    try:
        current_idx = stage_codes.index(current_stage)
    except ValueError:
        current_idx = 0

    is_last_stage = current_idx >= len(stage_codes) - 1

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with get_wf_db() as conn:
        cursor = conn.cursor()

        if is_last_stage:
            cursor.execute('''
                UPDATE sample_tasks 
                SET task_status = 'completed', completed_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (now, task_id))
        else:
            next_stage = stage_codes[current_idx + 1]
            next_stage_info = get_stage_by_code(next_stage)
            default_hours = next_stage_info.get('default_deadline_hours', 24) if next_stage_info else 24
            next_deadline = (datetime.now() + timedelta(hours=default_hours)).strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute('''
                UPDATE sample_tasks 
                SET current_stage = ?, task_status = 'pending',
                    deadline = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (next_stage, next_deadline, task_id))

        cursor.execute('''
            INSERT INTO task_stage_logs 
            (task_id, sample_id, stage_code, action, status, operator, comment)
            VALUES (?, ?, ?, 'complete', 'completed', ?, ?)
        ''', (task_id, task['sample_id'], current_stage, operator, comment))

    _log_wf_operation('complete_stage', 'task', task_id, task['sample_no'],
                      f'完成阶段 {current_stage}', operator)

    return not is_last_stage


def return_task(task_id, operator, return_reason='', return_to_stage=None):
    task = get_task(task_id)
    if not task:
        return False

    current_stage = task['current_stage']

    if return_to_stage is None:
        stages = get_stages()
        stage_codes = [s['stage_code'] for s in stages]
        try:
            current_idx = stage_codes.index(current_stage)
            return_to_stage = stage_codes[max(0, current_idx - 1)]
        except ValueError:
            return_to_stage = current_stage

    stage_info = get_stage_by_code(return_to_stage)
    default_hours = stage_info.get('default_deadline_hours', 24) if stage_info else 24
    new_deadline = (datetime.now() + timedelta(hours=default_hours)).strftime('%Y-%m-%d %H:%M:%S')

    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE sample_tasks 
            SET current_stage = ?, task_status = 'returned',
                deadline = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (return_to_stage, new_deadline, task_id))

        cursor.execute('''
            INSERT INTO task_stage_logs 
            (task_id, sample_id, stage_code, action, status, operator, comment)
            VALUES (?, ?, ?, 'return', 'returned', ?, ?)
        ''', (task_id, task['sample_id'], current_stage, operator,
              f'退回至 {return_to_stage}：{return_reason}'))

    _log_wf_operation('return_task', 'task', task_id, task['sample_no'],
                      f'任务退回至 {return_to_stage}，原因：{return_reason}', operator)

    return True


def add_approval(task_id, stage_code, approver, result, comment=''):
    task = get_task(task_id)
    if not task:
        return False

    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO approvals 
            (task_id, sample_id, stage_code, approver, approval_result, comment)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (task_id, task['sample_id'], stage_code, approver, result, comment))

        approval_id = cursor.lastrowid

    _log_wf_operation('approval', 'task', task_id, task['sample_no'],
                      f'{approver} {result} - {comment}', approver)

    return approval_id


def get_task_stage_logs(task_id):
    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM task_stage_logs 
            WHERE task_id = ? 
            ORDER BY acted_at DESC, id DESC
        ''', (task_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_approvals(task_id):
    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM approvals 
            WHERE task_id = ? 
            ORDER BY signed_at DESC
        ''', (task_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_overdue_tasks():
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.*, s.sampling_site, s.eruption_layer, s.group_name
            FROM sample_tasks t
            LEFT JOIN samples s ON t.sample_id = s.id
            WHERE t.deadline < ? 
              AND t.task_status IN ('pending', 'in_progress')
              AND t.task_status != 'completed'
            ORDER BY t.deadline ASC
        ''', (now,))
        return [dict(row) for row in cursor.fetchall()]


def get_user_tasks(username, status=None):
    with get_wf_db() as conn:
        cursor = conn.cursor()
        query = '''
            SELECT t.*, s.sampling_site, s.eruption_layer, s.group_name
            FROM sample_tasks t
            LEFT JOIN samples s ON t.sample_id = s.id
            WHERE t.assigned_to = ?
        '''
        params = [username]
        if status:
            query += ' AND t.task_status = ?'
            params.append(status)
        query += ' ORDER BY t.priority DESC, t.created_at DESC'
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_workflow_statistics():
    with get_wf_db() as conn:
        cursor = conn.cursor()

        stats = {}

        cursor.execute('SELECT COUNT(*) as total FROM sample_tasks')
        stats['total_tasks'] = cursor.fetchone()['total']

        cursor.execute('''
            SELECT task_status, COUNT(*) as count 
            FROM sample_tasks 
            GROUP BY task_status
        ''')
        stats['by_status'] = {row['task_status']: row['count'] for row in cursor.fetchall()}

        cursor.execute('''
            SELECT current_stage, COUNT(*) as count 
            FROM sample_tasks 
            WHERE task_status != 'completed'
            GROUP BY current_stage
        ''')
        stats['by_stage'] = {row['current_stage']: row['count'] for row in cursor.fetchall()}

        cursor.execute('''
            SELECT assigned_to, COUNT(*) as count 
            FROM sample_tasks 
            WHERE assigned_to IS NOT NULL AND task_status != 'completed'
            GROUP BY assigned_to
        ''')
        stats['by_assignee'] = {row['assigned_to']: row['count'] for row in cursor.fetchall()}

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            SELECT COUNT(*) as count 
            FROM sample_tasks 
            WHERE deadline < ? AND task_status IN ('pending', 'in_progress')
        ''', (now,))
        stats['overdue_count'] = cursor.fetchone()['count']

        return stats


def _log_wf_operation(operation_type, entity_type=None, entity_id=None, entity_name=None,
                      details=None, operator='system'):
    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO operation_logs (operation_type, entity_type, entity_id, entity_name, details, operator)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (operation_type, entity_type, entity_id, entity_name, details, operator))


def update_task_deadline(task_id, deadline, operator='system'):
    task = get_task(task_id)
    if not task:
        return False

    with get_wf_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE sample_tasks 
            SET deadline = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (deadline, task_id))

        cursor.execute('''
            INSERT INTO task_stage_logs 
            (task_id, sample_id, stage_code, action, status, operator, deadline, comment)
            VALUES (?, ?, ?, 'update_deadline', ?, ?, ?, '调整截止时间')
        ''', (task_id, task['sample_id'], task['current_stage'], task['task_status'],
              operator, deadline))

    _log_wf_operation('update_deadline', 'task', task_id, task['sample_no'],
                      f'调整截止时间为 {deadline}', operator)

    return True


def get_stage_name(code):
    stage_map = {s['code']: s['name'] for s in WORKFLOW_STAGES}
    return stage_map.get(code, code)


def get_status_name(status):
    return TASK_STATUS.get(status, status)


def get_priority_name(priority):
    priority_map = {
        'high': '高',
        'normal': '普通',
        'low': '低',
    }
    return priority_map.get(priority, priority)
