import sqlite3
import os
import json
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "volcanic_ash.db")


@contextmanager
def get_db():
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


def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_no TEXT UNIQUE NOT NULL,
                sampling_site TEXT NOT NULL,
                eruption_layer TEXT,
                total_weight REAL NOT NULL,
                description TEXT,
                group_name TEXT,
                sampling_time TEXT,
                depth REAL,
                profile_position TEXT,
                latitude REAL,
                longitude REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        _migrate_samples_table(cursor)
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sieve_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER NOT NULL,
                sieve_size REAL NOT NULL,
                retained_weight REAL NOT NULL,
                FOREIGN KEY (sample_id) REFERENCES samples (id) ON DELETE CASCADE,
                UNIQUE (sample_id, sieve_size)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sieve_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                sizes TEXT NOT NULL,
                is_default INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_type TEXT NOT NULL,
                entity_type TEXT,
                entity_id INTEGER,
                entity_name TEXT,
                details TEXT,
                operator TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        default_sizes = [63.0, 31.5, 16.0, 8.0, 4.0, 2.0, 1.0, 0.5, 0.25, 0.125, 0.063]
        cursor.execute('''
            INSERT OR IGNORE INTO sieve_sets (name, sizes, is_default)
            VALUES (?, ?, ?)
        ''', ('标准火山灰粒级', ','.join(map(str, default_sizes)), 1))


def _migrate_samples_table(cursor):
    cursor.execute("PRAGMA table_info(samples)")
    columns = [row['name'] for row in cursor.fetchall()]
    
    new_columns = {
        'group_name': 'TEXT',
        'sampling_time': 'TEXT',
        'depth': 'REAL',
        'profile_position': 'TEXT',
        'latitude': 'REAL',
        'longitude': 'REAL',
    }
    
    for col_name, col_type in new_columns.items():
        if col_name not in columns:
            cursor.execute(f'ALTER TABLE samples ADD COLUMN {col_name} {col_type}')


def log_operation(operation_type, entity_type=None, entity_id=None, entity_name=None, details=None, operator='system'):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO operation_logs (operation_type, entity_type, entity_id, entity_name, details, operator)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (operation_type, entity_type, entity_id, entity_name, details, operator))


def get_all_samples():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, 
                   (SELECT COUNT(*) FROM sieve_data d WHERE d.sample_id = s.id) as sieve_count
            FROM samples s
            ORDER BY s.created_at DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]


def get_samples_by_group(group_name):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*,
                   (SELECT COUNT(*) FROM sieve_data d WHERE d.sample_id = s.id) as sieve_count
            FROM samples s
            WHERE s.group_name = ?
            ORDER BY s.depth ASC, s.sampling_time ASC
        ''', (group_name,))
        return [dict(row) for row in cursor.fetchall()]


def get_all_groups():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT group_name 
            FROM samples 
            WHERE group_name IS NOT NULL AND group_name != ''
            ORDER BY group_name
        ''')
        return [row['group_name'] for row in cursor.fetchall()]


def get_sample(sample_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM samples WHERE id = ?', (sample_id,))
        sample = cursor.fetchone()
        if sample:
            sample = dict(sample)
            cursor.execute('''
                SELECT * FROM sieve_data 
                WHERE sample_id = ? 
                ORDER BY sieve_size DESC
            ''', (sample_id,))
            sample['sieve_data'] = [dict(row) for row in cursor.fetchall()]
        return sample


def get_sample_by_no(sample_no):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM samples WHERE sample_no = ?', (sample_no,))
        row = cursor.fetchone()
        return dict(row) if row else None


def add_sample(sample_no, sampling_site, eruption_layer, total_weight, description="",
               group_name=None, sampling_time=None, depth=None, profile_position=None,
               latitude=None, longitude=None):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO samples (sample_no, sampling_site, eruption_layer, total_weight, description,
                                 group_name, sampling_time, depth, profile_position, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (sample_no, sampling_site, eruption_layer, total_weight, description,
              group_name, sampling_time, depth, profile_position, latitude, longitude))
        sample_id = cursor.lastrowid
        
    log_operation('create', 'sample', sample_id, sample_no, f'创建样本 {sample_no}')
    return sample_id


def update_sample(sample_id, sample_no, sampling_site, eruption_layer, total_weight, description="",
                  group_name=None, sampling_time=None, depth=None, profile_position=None,
                  latitude=None, longitude=None):
    sample = get_sample(sample_id)
    old_name = sample['sample_no'] if sample else str(sample_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE samples 
            SET sample_no = ?, sampling_site = ?, eruption_layer = ?, 
                total_weight = ?, description = ?, updated_at = CURRENT_TIMESTAMP,
                group_name = ?, sampling_time = ?, depth = ?, profile_position = ?,
                latitude = ?, longitude = ?
            WHERE id = ?
        ''', (sample_no, sampling_site, eruption_layer, total_weight, description,
              group_name, sampling_time, depth, profile_position, latitude, longitude, sample_id))
        result = cursor.rowcount > 0
    
    if result:
        log_operation('update', 'sample', sample_id, sample_no, 
                     f'更新样本 {old_name} → {sample_no}')
    return result


def delete_sample(sample_id):
    sample = get_sample(sample_id)
    sample_name = sample['sample_no'] if sample else str(sample_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sieve_data WHERE sample_id = ?', (sample_id,))
        cursor.execute('DELETE FROM samples WHERE id = ?', (sample_id,))
        result = cursor.rowcount > 0
    
    if result:
        log_operation('delete', 'sample', sample_id, sample_name, f'删除样本 {sample_name}')
    return result


def batch_delete_samples(sample_ids):
    deleted = []
    for sid in sample_ids:
        sample = get_sample(sid)
        if sample and delete_sample(sid):
            deleted.append(sample['sample_no'])
    
    if deleted:
        log_operation('batch_delete', 'sample', None, None, 
                     f'批量删除 {len(deleted)} 个样本: {", ".join(deleted)}')
    return len(deleted)


def add_sieve_data(sample_id, sieve_size, retained_weight):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO sieve_data (sample_id, sieve_size, retained_weight)
            VALUES (?, ?, ?)
        ''', (sample_id, sieve_size, retained_weight))
        return cursor.lastrowid


def batch_add_sieve_data(sample_id, sieve_data_list):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sieve_data WHERE sample_id = ?', (sample_id,))
        for sieve_size, retained_weight in sieve_data_list:
            cursor.execute('''
                INSERT INTO sieve_data (sample_id, sieve_size, retained_weight)
                VALUES (?, ?, ?)
            ''', (sample_id, sieve_size, retained_weight))
    
    log_operation('update_sieve', 'sample', sample_id, None, 
                 f'更新样本筛分数据，共 {len(sieve_data_list)} 个粒级')


def delete_sieve_data(sieve_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sieve_data WHERE id = ?', (sieve_id,))
        return cursor.rowcount > 0


def get_default_sieve_sizes():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT sizes FROM sieve_sets WHERE is_default = 1 LIMIT 1')
        row = cursor.fetchone()
        if row:
            return [float(s) for s in row['sizes'].split(',')]
        return [63.0, 31.5, 16.0, 8.0, 4.0, 2.0, 1.0, 0.5, 0.25, 0.125, 0.063]


def get_operation_logs(limit=100, offset=0):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM operation_logs 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        return [dict(row) for row in cursor.fetchall()]


def batch_import_samples(samples_data):
    """
    批量导入样本数据
    samples_data: list of dicts, each with sample info and sieve_data list
    Returns: (success_count, failed_count, errors)
    """
    success_count = 0
    failed_count = 0
    errors = []
    
    for i, data in enumerate(samples_data):
        try:
            sample_no = data.get('sample_no', '').strip()
            if not sample_no:
                failed_count += 1
                errors.append(f"第 {i+1} 条：样本编号不能为空")
                continue
            
            existing = get_sample_by_no(sample_no)
            if existing:
                failed_count += 1
                errors.append(f"第 {i+1} 条：样本编号 {sample_no} 已存在")
                continue
            
            sampling_site = data.get('sampling_site', '').strip()
            if not sampling_site:
                failed_count += 1
                errors.append(f"第 {i+1} 条：采样点不能为空")
                continue
            
            total_weight = float(data.get('total_weight', 0))
            if total_weight <= 0:
                failed_count += 1
                errors.append(f"第 {i+1} 条：总重量必须大于 0")
                continue
            
            sample_id = add_sample(
                sample_no=sample_no,
                sampling_site=sampling_site,
                eruption_layer=data.get('eruption_layer', '').strip(),
                total_weight=total_weight,
                description=data.get('description', '').strip(),
                group_name=data.get('group_name', '').strip() or None,
                sampling_time=data.get('sampling_time', '').strip() or None,
                depth=float(data['depth']) if data.get('depth') not in (None, '', 'None') else None,
                profile_position=data.get('profile_position', '').strip() or None,
                latitude=float(data['latitude']) if data.get('latitude') not in (None, '', 'None') else None,
                longitude=float(data['longitude']) if data.get('longitude') not in (None, '', 'None') else None,
            )
            
            sieve_data_list = data.get('sieve_data', [])
            if sieve_data_list:
                sieve_list = []
                for sd in sieve_data_list:
                    sieve_size = float(sd.get('sieve_size', 0))
                    retained_weight = float(sd.get('retained_weight', 0))
                    if sieve_size > 0 and retained_weight >= 0:
                        sieve_list.append((sieve_size, retained_weight))
                if sieve_list:
                    batch_add_sieve_data(sample_id, sieve_list)
            
            success_count += 1
        except Exception as e:
            failed_count += 1
            errors.append(f"第 {i+1} 条：{str(e)}")
    
    log_operation('batch_import', 'sample', None, None, 
                 f'批量导入样本，成功 {success_count} 条，失败 {failed_count} 条')
    
    return success_count, failed_count, errors
