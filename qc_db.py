import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
import json

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "volcanic_ash.db")

BATCH_STATUS = {
    "planning": "计划中",
    "in_progress": "进行中",
    "completed": "已完成",
    "cancelled": "已取消",
}

CALIBRATION_STATUS = {
    "pending": "待校准",
    "in_progress": "校准中",
    "passed": "合格",
    "failed": "不合格",
}

QC_ALERT_LEVEL = {
    "info": "提示",
    "warning": "警告",
    "error": "严重",
}

RETEST_STATUS = {
    "pending": "待审批",
    "approved": "已批准",
    "rejected": "已拒绝",
    "completed": "已完成",
}

PARALLEL_TYPE = {
    "duplicate": "重复样",
    "parallel": "平行样",
    "blank": "空白样",
    "standard": "标准样",
}


@contextmanager
def get_qc_db():
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


def init_qc_db():
    with get_qc_db() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS experiment_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_no TEXT UNIQUE NOT NULL,
                batch_name TEXT,
                batch_type TEXT DEFAULT 'sieving',
                status TEXT DEFAULT 'planning',
                start_date TEXT,
                end_date TEXT,
                operator TEXT,
                description TEXT,
                total_samples INTEGER DEFAULT 0,
                created_by TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS batch_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                sample_id INTEGER NOT NULL,
                sample_no TEXT NOT NULL,
                position_no INTEGER,
                added_by TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES experiment_batches (id) ON DELETE CASCADE,
                FOREIGN KEY (sample_id) REFERENCES samples (id) ON DELETE CASCADE,
                UNIQUE (batch_id, sample_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS instruments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_code TEXT UNIQUE NOT NULL,
                instrument_name TEXT NOT NULL,
                instrument_type TEXT,
                model TEXT,
                manufacturer TEXT,
                serial_no TEXT,
                location TEXT,
                calibration_cycle_days INTEGER DEFAULT 365,
                last_calibration_date TEXT,
                next_calibration_date TEXT,
                status TEXT DEFAULT 'active',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS instrument_calibrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_id INTEGER NOT NULL,
                calibration_date TEXT NOT NULL,
                calibration_type TEXT DEFAULT 'routine',
                status TEXT DEFAULT 'pending',
                calibrator TEXT,
                certificate_no TEXT,
                calibration_method TEXT,
                standard_reference TEXT,
                results_data TEXT,
                uncertainty REAL,
                pass_criteria TEXT,
                conclusion TEXT,
                next_calibration_date TEXT,
                cost REAL,
                remarks TEXT,
                created_by TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instrument_id) REFERENCES instruments (id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS qc_standards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                standard_code TEXT UNIQUE NOT NULL,
                standard_name TEXT NOT NULL,
                parameter_name TEXT,
                unit TEXT,
                target_value REAL,
                tolerance_plus REAL,
                tolerance_minus REAL,
                warning_threshold_pct REAL DEFAULT 80,
                method TEXT,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parallel_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER,
                parent_sample_id INTEGER NOT NULL,
                parent_sample_no TEXT NOT NULL,
                parallel_sample_id INTEGER,
                parallel_sample_no TEXT,
                parallel_type TEXT NOT NULL,
                parameter TEXT,
                original_value REAL,
                parallel_value REAL,
                difference REAL,
                relative_deviation REAL,
                tolerance_pct REAL,
                is_pass INTEGER DEFAULT 1,
                comparison_date TEXT,
                operator TEXT,
                remarks TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES experiment_batches (id) ON DELETE SET NULL,
                FOREIGN KEY (parent_sample_id) REFERENCES samples (id) ON DELETE CASCADE,
                FOREIGN KEY (parallel_sample_id) REFERENCES samples (id) ON DELETE SET NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS qc_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                alert_level TEXT DEFAULT 'warning',
                related_entity_type TEXT,
                related_entity_id INTEGER,
                related_entity_name TEXT,
                title TEXT NOT NULL,
                message TEXT,
                parameter TEXT,
                actual_value REAL,
                expected_value REAL,
                threshold REAL,
                is_acknowledged INTEGER DEFAULT 0,
                acknowledged_by TEXT,
                acknowledged_at TEXT,
                remarks TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS retest_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER NOT NULL,
                sample_no TEXT NOT NULL,
                request_no TEXT UNIQUE NOT NULL,
                request_type TEXT DEFAULT 'abnormal',
                reason TEXT NOT NULL,
                requested_by TEXT,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                approver TEXT,
                approval_comment TEXT,
                approved_at TEXT,
                retest_sample_id INTEGER,
                retest_result TEXT,
                completed_at TEXT,
                remarks TEXT,
                FOREIGN KEY (sample_id) REFERENCES samples (id) ON DELETE CASCADE,
                FOREIGN KEY (retest_sample_id) REFERENCES samples (id) ON DELETE SET NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS qc_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_no TEXT UNIQUE NOT NULL,
                report_type TEXT NOT NULL,
                title TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                summary_data TEXT,
                generated_by TEXT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'draft'
            )
        ''')

        _init_default_instruments(cursor)
        _init_default_qc_standards(cursor)
        _migrate_qc_tables(cursor)


def _init_default_instruments(cursor):
    default_instruments = [
        ("INST-001", "标准试验筛组", "sieve", "ISO 3310-1", "Retsch", "S2024-001", "实验室A-01", 365, None, None, "active", "火山灰筛分专用标准筛"),
        ("INST-002", "电子分析天平", "balance", "ME204E", "Mettler Toledo", "B2024-005", "实验室A-02", 180, None, None, "active", "0.1mg精度分析天平"),
        ("INST-003", "振筛机", "shaker", "AS200", "Retsch", "R2024-003", "实验室A-01", 365, None, None, "active", "电磁式振筛机"),
        ("INST-004", "烘箱", "oven", "FD115", "Binder", "O2024-002", "实验室B-01", 365, None, None, "active", "精密控温烘箱"),
    ]
    for inst in default_instruments:
        cursor.execute('''
            INSERT OR IGNORE INTO instruments 
            (instrument_code, instrument_name, instrument_type, model, manufacturer, 
             serial_no, location, calibration_cycle_days, last_calibration_date, 
             next_calibration_date, status, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', inst)


def _init_default_qc_standards(cursor):
    default_standards = [
        ("QC-001", "平行样偏差标准", "D50", "mm", None, None, None, 10.0, "筛分", "平行样D50相对偏差允许范围", 1),
        ("QC-002", "筛分回收率标准", "回收率", "%", 100.0, 2.0, 2.0, 95.0, "重量法", "筛分回收率允许范围98%-102%", 1),
        ("QC-003", "重复样精密度标准", "D50", "mm", None, None, None, 5.0, "重复测试", "重复样D50相对偏差≤5%", 1),
    ]
    for std in default_standards:
        cursor.execute('''
            INSERT OR IGNORE INTO qc_standards 
            (standard_code, standard_name, parameter_name, unit, target_value, 
             tolerance_plus, tolerance_minus, warning_threshold_pct, method, 
             description, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', std)


def _migrate_qc_tables(cursor):
    tables_to_check = {
        'experiment_batches': ['total_samples'],
        'instruments': ['last_calibration_date', 'next_calibration_date'],
    }
    for table_name, columns in tables_to_check.items():
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_cols = [row['name'] for row in cursor.fetchall()]
        for col in columns:
            if col not in existing_cols:
                col_type = 'INTEGER DEFAULT 0' if col == 'total_samples' else 'TEXT'
                cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {col} {col_type}')


def _log_qc_operation(operation_type, entity_type=None, entity_id=None, entity_name=None,
                       details=None, operator='system'):
    try:
        with get_qc_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO operation_logs (operation_type, entity_type, entity_id, entity_name, details, operator)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (operation_type, entity_type, entity_id, entity_name, details, operator))
    except Exception:
        pass


# ==================== 实验批次管理 ====================

def create_batch(batch_no, batch_name=None, batch_type='sieving', status='planning',
                 start_date=None, end_date=None, operator=None, description=None,
                 created_by='system'):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO experiment_batches 
            (batch_no, batch_name, batch_type, status, start_date, end_date, 
             operator, description, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (batch_no, batch_name or batch_no, batch_type, status, start_date, end_date,
              operator, description, created_by))
        batch_id = cursor.lastrowid

    _log_qc_operation('create_batch', 'batch', batch_id, batch_no,
                      f'创建实验批次 {batch_no}', created_by)
    return batch_id


def get_batch(batch_id):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM experiment_batches WHERE id = ?', (batch_id,))
        batch = cursor.fetchone()
        if batch:
            batch = dict(batch)
            cursor.execute('''
                SELECT bs.*, s.sampling_site, s.total_weight, s.group_name
                FROM batch_samples bs
                LEFT JOIN samples s ON bs.sample_id = s.id
                WHERE bs.batch_id = ?
                ORDER BY bs.position_no, bs.added_at
            ''', (batch_id,))
            batch['samples'] = [dict(row) for row in cursor.fetchall()]
        return batch


def get_batch_by_no(batch_no):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM experiment_batches WHERE batch_no = ?', (batch_no,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_batches(status=None, batch_type=None, operator=None, date_from=None, date_to=None):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        query = 'SELECT * FROM experiment_batches WHERE 1=1'
        params = []

        if status:
            query += ' AND status = ?'
            params.append(status)
        if batch_type:
            query += ' AND batch_type = ?'
            params.append(batch_type)
        if operator:
            query += ' AND operator = ?'
            params.append(operator)
        if date_from:
            query += ' AND start_date >= ?'
            params.append(date_from)
        if date_to:
            query += ' AND end_date <= ?'
            params.append(date_to)

        query += ' ORDER BY created_at DESC'
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_batch(batch_id, **kwargs):
    batch = get_batch(batch_id)
    if not batch:
        return False

    allowed_fields = ['batch_name', 'batch_type', 'status', 'start_date', 'end_date',
                      'operator', 'description']
    update_fields = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not update_fields:
        return False

    set_clause = ', '.join([f'{k} = ?' for k in update_fields.keys()])
    set_clause += ', updated_at = CURRENT_TIMESTAMP'
    params = list(update_fields.values()) + [batch_id]

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f'UPDATE experiment_batches SET {set_clause} WHERE id = ?', params)
        result = cursor.rowcount > 0

    if result:
        _log_qc_operation('update_batch', 'batch', batch_id, batch.get('batch_no'),
                          f'更新批次信息', kwargs.get('operator', 'system'))
    return result


def delete_batch(batch_id):
    batch = get_batch(batch_id)
    if not batch:
        return False

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM batch_samples WHERE batch_id = ?', (batch_id,))
        cursor.execute('DELETE FROM experiment_batches WHERE id = ?', (batch_id,))
        result = cursor.rowcount > 0

    if result:
        _log_qc_operation('delete_batch', 'batch', batch_id, batch.get('batch_no'),
                          f'删除批次 {batch.get("batch_no")}')
    return result


def add_sample_to_batch(batch_id, sample_id, sample_no, position_no=None, added_by='system'):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO batch_samples (batch_id, sample_id, sample_no, position_no, added_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (batch_id, sample_id, sample_no, position_no, added_by))

            cursor.execute('''
                UPDATE experiment_batches 
                SET total_samples = (SELECT COUNT(*) FROM batch_samples WHERE batch_id = ?),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (batch_id, batch_id))

            _log_qc_operation('add_batch_sample', 'batch', batch_id, sample_no,
                              f'向批次添加样本 {sample_no}', added_by)
            return True
        except sqlite3.IntegrityError:
            return False


def remove_sample_from_batch(batch_id, sample_id):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM batch_samples WHERE batch_id = ? AND sample_id = ?
        ''', (batch_id, sample_id))
        result = cursor.rowcount > 0

        if result:
            cursor.execute('''
                UPDATE experiment_batches 
                SET total_samples = (SELECT COUNT(*) FROM batch_samples WHERE batch_id = ?),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (batch_id, batch_id))

    if result:
        _log_qc_operation('remove_batch_sample', 'batch', batch_id, None,
                          f'从批次移除样本 {sample_id}')
    return result


def get_batch_samples(batch_id):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT bs.*, s.sampling_site, s.total_weight, s.group_name, s.sampling_time
            FROM batch_samples bs
            LEFT JOIN samples s ON bs.sample_id = s.id
            WHERE bs.batch_id = ?
            ORDER BY bs.position_no, bs.added_at
        ''', (batch_id,))
        return [dict(row) for row in cursor.fetchall()]


# ==================== 仪器管理 ====================

def create_instrument(instrument_code, instrument_name, instrument_type=None, model=None,
                      manufacturer=None, serial_no=None, location=None,
                      calibration_cycle_days=365, description=None):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO instruments 
                (instrument_code, instrument_name, instrument_type, model, manufacturer,
                 serial_no, location, calibration_cycle_days, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (instrument_code, instrument_name, instrument_type, model, manufacturer,
                  serial_no, location, calibration_cycle_days, description))
            inst_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    _log_qc_operation('create_instrument', 'instrument', inst_id, instrument_code,
                      f'创建仪器 {instrument_name}')
    return inst_id


def get_instrument(inst_id):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM instruments WHERE id = ?', (inst_id,))
        instrument = cursor.fetchone()
        if instrument:
            instrument = dict(instrument)
            cursor.execute('''
                SELECT * FROM instrument_calibrations 
                WHERE instrument_id = ? 
                ORDER BY calibration_date DESC, id DESC
            ''', (inst_id,))
            instrument['calibrations'] = [dict(row) for row in cursor.fetchall()]
        return instrument


def get_all_instruments(status=None, instrument_type=None):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        query = 'SELECT * FROM instruments WHERE 1=1'
        params = []

        if status:
            query += ' AND status = ?'
            params.append(status)
        if instrument_type:
            query += ' AND instrument_type = ?'
            params.append(instrument_type)

        query += ' ORDER BY instrument_code'
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_instrument(inst_id, **kwargs):
    inst = get_instrument(inst_id)
    if not inst:
        return False

    allowed_fields = ['instrument_name', 'instrument_type', 'model', 'manufacturer',
                      'serial_no', 'location', 'calibration_cycle_days', 'status',
                      'description', 'last_calibration_date', 'next_calibration_date']
    update_fields = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not update_fields:
        return False

    set_clause = ', '.join([f'{k} = ?' for k in update_fields.keys()])
    set_clause += ', updated_at = CURRENT_TIMESTAMP'
    params = list(update_fields.values()) + [inst_id]

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f'UPDATE instruments SET {set_clause} WHERE id = ?', params)
        result = cursor.rowcount > 0

    if result:
        _log_qc_operation('update_instrument', 'instrument', inst_id,
                          inst.get('instrument_code'), f'更新仪器信息')
    return result


def delete_instrument(inst_id):
    inst = get_instrument(inst_id)
    if not inst:
        return False

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM instrument_calibrations WHERE instrument_id = ?', (inst_id,))
        cursor.execute('DELETE FROM instruments WHERE id = ?', (inst_id,))
        result = cursor.rowcount > 0

    if result:
        _log_qc_operation('delete_instrument', 'instrument', inst_id,
                          inst.get('instrument_code'), f'删除仪器 {inst.get("instrument_name")}')
    return result


# ==================== 仪器校准记录 ====================

def add_calibration(instrument_id, calibration_date, calibration_type='routine',
                    status='pending', calibrator=None, certificate_no=None,
                    calibration_method=None, standard_reference=None, results_data=None,
                    uncertainty=None, pass_criteria=None, conclusion=None,
                    next_calibration_date=None, cost=None, remarks=None, created_by='system'):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO instrument_calibrations 
            (instrument_id, calibration_date, calibration_type, status, calibrator,
             certificate_no, calibration_method, standard_reference, results_data,
             uncertainty, pass_criteria, conclusion, next_calibration_date, cost,
             remarks, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (instrument_id, calibration_date, calibration_type, status, calibrator,
              certificate_no, calibration_method, standard_reference,
              json.dumps(results_data) if results_data else None,
              uncertainty, pass_criteria, conclusion, next_calibration_date,
              cost, remarks, created_by))
        cal_id = cursor.lastrowid

        if status == 'passed':
            cursor.execute('''
                UPDATE instruments 
                SET last_calibration_date = ?, next_calibration_date = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (calibration_date, next_calibration_date, instrument_id))

    _log_qc_operation('add_calibration', 'calibration', cal_id, certificate_no,
                      f'添加仪器校准记录，状态: {status}', created_by)
    return cal_id


def get_calibration(cal_id):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM instrument_calibrations WHERE id = ?', (cal_id,))
        row = cursor.fetchone()
        if row:
            data = dict(row)
            if data.get('results_data'):
                try:
                    data['results_data'] = json.loads(data['results_data'])
                except (json.JSONDecodeError, TypeError):
                    pass
            return data
        return None


def get_instrument_calibrations(instrument_id):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM instrument_calibrations 
            WHERE instrument_id = ? 
            ORDER BY calibration_date DESC, id DESC
        ''', (instrument_id,))
        results = []
        for row in cursor.fetchall():
            data = dict(row)
            if data.get('results_data'):
                try:
                    data['results_data'] = json.loads(data['results_data'])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(data)
        return results


def get_calibrations_needing_reminder(days_ahead=30):
    today = datetime.now().date()
    target_date = today + timedelta(days=days_ahead)
    target_str = target_date.strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT i.*, c.calibration_date as last_cal_date
            FROM instruments i
            LEFT JOIN instrument_calibrations c ON i.id = c.instrument_id
            WHERE i.status = 'active'
              AND i.next_calibration_date IS NOT NULL
              AND i.next_calibration_date <= ?
              AND i.next_calibration_date >= ?
            ORDER BY i.next_calibration_date ASC
        ''', (target_str, today_str))
        return [dict(row) for row in cursor.fetchall()]


def get_overdue_calibrations():
    today_str = datetime.now().strftime('%Y-%m-%d')

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT i.*
            FROM instruments i
            WHERE i.status = 'active'
              AND i.next_calibration_date IS NOT NULL
              AND i.next_calibration_date < ?
            ORDER BY i.next_calibration_date ASC
        ''', (today_str,))
        return [dict(row) for row in cursor.fetchall()]


# ==================== 平行样/重复样对比 ====================

def add_parallel_sample(batch_id=None, parent_sample_id=None, parent_sample_no=None,
                        parallel_sample_id=None, parallel_sample_no=None,
                        parallel_type='duplicate', parameter='D50',
                        original_value=None, parallel_value=None,
                        tolerance_pct=5.0, comparison_date=None,
                        operator=None, remarks=None):
    if original_value is not None and parallel_value is not None:
        difference = abs(original_value - parallel_value)
        if original_value != 0:
            relative_deviation = (difference / abs(original_value)) * 100
        else:
            relative_deviation = 0.0
        is_pass = 1 if relative_deviation <= tolerance_pct else 0
    else:
        difference = None
        relative_deviation = None
        is_pass = 1

    if comparison_date is None:
        comparison_date = datetime.now().strftime('%Y-%m-%d')

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO parallel_samples 
            (batch_id, parent_sample_id, parent_sample_no, parallel_sample_id,
             parallel_sample_no, parallel_type, parameter, original_value,
             parallel_value, difference, relative_deviation, tolerance_pct,
             is_pass, comparison_date, operator, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (batch_id, parent_sample_id, parent_sample_no, parallel_sample_id,
              parallel_sample_no, parallel_type, parameter, original_value,
              parallel_value, difference, relative_deviation, tolerance_pct,
              is_pass, comparison_date, operator, remarks))
        ps_id = cursor.lastrowid

    _log_qc_operation('add_parallel', 'qc', ps_id, f'{parent_sample_no}/{parallel_type}',
                      f'添加{parallel_type}对比，{"合格" if is_pass else "不合格"}', operator)
    return ps_id


def get_parallel_sample(ps_id):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM parallel_samples WHERE id = ?', (ps_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_parallel_samples(batch_id=None, parallel_type=None, is_pass=None,
                          sample_id=None, date_from=None, date_to=None):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        query = 'SELECT * FROM parallel_samples WHERE 1=1'
        params = []

        if batch_id:
            query += ' AND batch_id = ?'
            params.append(batch_id)
        if parallel_type:
            query += ' AND parallel_type = ?'
            params.append(parallel_type)
        if is_pass is not None:
            query += ' AND is_pass = ?'
            params.append(1 if is_pass else 0)
        if sample_id:
            query += ' AND (parent_sample_id = ? OR parallel_sample_id = ?)'
            params.extend([sample_id, sample_id])
        if date_from:
            query += ' AND comparison_date >= ?'
            params.append(date_from)
        if date_to:
            query += ' AND comparison_date <= ?'
            params.append(date_to)

        query += ' ORDER BY created_at DESC'
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def calculate_parallel_stats(parallel_type=None, date_from=None, date_to=None):
    records = get_parallel_samples(parallel_type=parallel_type,
                                   date_from=date_from, date_to=date_to)
    if not records:
        return {'total': 0, 'passed': 0, 'failed': 0, 'pass_rate': 0, 'avg_deviation': 0}

    passed = sum(1 for r in records if r.get('is_pass') == 1)
    failed = len(records) - passed
    deviations = [r['relative_deviation'] for r in records
                  if r.get('relative_deviation') is not None]
    avg_deviation = sum(deviations) / len(deviations) if deviations else 0

    return {
        'total': len(records),
        'passed': passed,
        'failed': failed,
        'pass_rate': (passed / len(records) * 100) if records else 0,
        'avg_deviation': avg_deviation,
    }


# ==================== 质量预警 ====================

def create_alert(alert_type, alert_level='warning', title='', message='',
                 related_entity_type=None, related_entity_id=None,
                 related_entity_name=None, parameter=None,
                 actual_value=None, expected_value=None, threshold=None,
                 remarks=None):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO qc_alerts 
            (alert_type, alert_level, title, message, related_entity_type,
             related_entity_id, related_entity_name, parameter, actual_value,
             expected_value, threshold, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (alert_type, alert_level, title, message, related_entity_type,
              related_entity_id, related_entity_name, parameter, actual_value,
              expected_value, threshold, remarks))
        alert_id = cursor.lastrowid

    _log_qc_operation('create_alert', 'alert', alert_id, title,
                      f'创建质量预警: {alert_level} - {title}')
    return alert_id


def get_alert(alert_id):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM qc_alerts WHERE id = ?', (alert_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_alerts(alert_level=None, alert_type=None, acknowledged=None,
               related_entity_type=None, limit=100, offset=0):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        query = 'SELECT * FROM qc_alerts WHERE 1=1'
        params = []

        if alert_level:
            query += ' AND alert_level = ?'
            params.append(alert_level)
        if alert_type:
            query += ' AND alert_type = ?'
            params.append(alert_type)
        if acknowledged is not None:
            query += ' AND is_acknowledged = ?'
            params.append(1 if acknowledged else 0)
        if related_entity_type:
            query += ' AND related_entity_type = ?'
            params.append(related_entity_type)

        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def acknowledge_alert(alert_id, acknowledged_by='system', remarks=None):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE qc_alerts 
            SET is_acknowledged = 1, acknowledged_by = ?, acknowledged_at = ?, remarks = ?
            WHERE id = ?
        ''', (acknowledged_by, now, remarks, alert_id))
        result = cursor.rowcount > 0

    if result:
        _log_qc_operation('ack_alert', 'alert', alert_id, None,
                          f'确认预警 #{alert_id}', acknowledged_by)
    return result


def get_alert_summary():
    with get_qc_db() as conn:
        cursor = conn.cursor()
        summary = {}

        cursor.execute('''
            SELECT alert_level, COUNT(*) as cnt 
            FROM qc_alerts 
            WHERE is_acknowledged = 0
            GROUP BY alert_level
        ''')
        summary['by_level_unack'] = {row['alert_level']: row['cnt']
                                      for row in cursor.fetchall()}

        cursor.execute('''
            SELECT alert_type, COUNT(*) as cnt 
            FROM qc_alerts 
            WHERE is_acknowledged = 0
            GROUP BY alert_type
        ''')
        summary['by_type_unack'] = {row['alert_type']: row['cnt']
                                     for row in cursor.fetchall()}

        cursor.execute('SELECT COUNT(*) as cnt FROM qc_alerts WHERE is_acknowledged = 0')
        summary['unacknowledged_count'] = cursor.fetchone()['cnt']

        return summary


def check_and_create_sieve_recovery_alert(sample_id, sample_no, recovery_pct):
    if recovery_pct < 98.0 or recovery_pct > 102.0:
        level = 'error' if (recovery_pct < 95.0 or recovery_pct > 105.0) else 'warning'
        title = f'样本 {sample_no} 筛分回收率异常'
        message = f'筛分回收率为 {recovery_pct:.2f}%，超出正常范围(98%-102%)'
        return create_alert(
            alert_type='recovery_abnormal',
            alert_level=level,
            title=title,
            message=message,
            related_entity_type='sample',
            related_entity_id=sample_id,
            related_entity_name=sample_no,
            parameter='筛分回收率',
            actual_value=recovery_pct,
            expected_value=100.0,
            threshold=2.0,
        )
    return None


# ==================== 复测申请 ====================

def create_retest_request(sample_id, sample_no, request_type='abnormal', reason='',
                          requested_by='system', remarks=None):
    now = datetime.now()
    request_no = f"RT{now.strftime('%Y%m%d%H%M%S')}"

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO retest_requests 
            (sample_id, sample_no, request_no, request_type, reason,
             requested_by, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (sample_id, sample_no, request_no, request_type, reason,
              requested_by, remarks))
        request_id = cursor.lastrowid

    _log_qc_operation('create_retest', 'retest', request_id, request_no,
                      f'创建复测申请 {request_no}', requested_by)
    return request_id, request_no


def get_retest_request(request_id):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM retest_requests WHERE id = ?', (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_retest_request_by_no(request_no):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM retest_requests WHERE request_no = ?', (request_no,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_retest_requests(status=None, sample_id=None, requested_by=None,
                        approver=None, date_from=None, date_to=None):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        query = 'SELECT * FROM retest_requests WHERE 1=1'
        params = []

        if status:
            query += ' AND status = ?'
            params.append(status)
        if sample_id:
            query += ' AND sample_id = ?'
            params.append(sample_id)
        if requested_by:
            query += ' AND requested_by = ?'
            params.append(requested_by)
        if approver:
            query += ' AND approver = ?'
            params.append(approver)
        if date_from:
            query += ' AND requested_at >= ?'
            params.append(date_from)
        if date_to:
            query += ' AND requested_at <= ?'
            params.append(date_to)

        query += ' ORDER BY requested_at DESC'
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def approve_retest(request_id, approver='system', comment=''):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE retest_requests 
            SET status = 'approved', approver = ?, approval_comment = ?, approved_at = ?
            WHERE id = ? AND status = 'pending'
        ''', (approver, comment, now, request_id))
        result = cursor.rowcount > 0

    if result:
        _log_qc_operation('approve_retest', 'retest', request_id, None,
                          f'批准复测申请 #{request_id}', approver)
    return result


def reject_retest(request_id, approver='system', comment=''):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE retest_requests 
            SET status = 'rejected', approver = ?, approval_comment = ?, approved_at = ?
            WHERE id = ? AND status = 'pending'
        ''', (approver, comment, now, request_id))
        result = cursor.rowcount > 0

    if result:
        _log_qc_operation('reject_retest', 'retest', request_id, None,
                          f'拒绝复测申请 #{request_id}', approver)
    return result


def complete_retest(request_id, retest_sample_id=None, retest_result='', remarks=None):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE retest_requests 
            SET status = 'completed', retest_sample_id = ?, retest_result = ?,
                completed_at = ?, remarks = ?
            WHERE id = ?
        ''', (retest_sample_id, retest_result, now, remarks, request_id))
        result = cursor.rowcount > 0

    if result:
        _log_qc_operation('complete_retest', 'retest', request_id, None,
                          f'完成复测 #{request_id}')
    return result


# ==================== 质量控制标准 ====================

def get_qc_standards(is_active=True):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        if is_active:
            cursor.execute('SELECT * FROM qc_standards WHERE is_active = 1 ORDER BY standard_code')
        else:
            cursor.execute('SELECT * FROM qc_standards ORDER BY standard_code')
        return [dict(row) for row in cursor.fetchall()]


def get_qc_standard(std_id):
    with get_qc_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM qc_standards WHERE id = ?', (std_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# ==================== 质量统计 ====================

def get_qc_dashboard_stats(date_from=None, date_to=None):
    stats = {}

    stats['batches'] = {
        'total': len(get_all_batches(date_from=date_from, date_to=date_to)),
        'in_progress': len(get_all_batches(status='in_progress')),
        'completed': len(get_all_batches(status='completed')),
    }

    instruments = get_all_instruments()
    stats['instruments'] = {
        'total': len(instruments),
        'active': len([i for i in instruments if i.get('status') == 'active']),
        'calibration_due': len(get_calibrations_needing_reminder(30)),
        'overdue': len(get_overdue_calibrations()),
    }

    parallel_stats = calculate_parallel_stats(date_from=date_from, date_to=date_to)
    stats['parallel_qc'] = parallel_stats

    stats['alerts'] = get_alert_summary()

    retest_pending = get_retest_requests(status='pending')
    retest_total = get_retest_requests(date_from=date_from, date_to=date_to)
    stats['retests'] = {
        'pending': len(retest_pending),
        'total': len(retest_total),
    }

    return stats


def get_batch_name(status_code):
    return BATCH_STATUS.get(status_code, status_code)


def get_calibration_status_name(status):
    return CALIBRATION_STATUS.get(status, status)


def get_alert_level_name(level):
    return QC_ALERT_LEVEL.get(level, level)


def get_retest_status_name(status):
    return RETEST_STATUS.get(status, status)


def get_parallel_type_name(ptype):
    return PARALLEL_TYPE.get(ptype, ptype)
