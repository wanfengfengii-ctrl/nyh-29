import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "volcanic_ash.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
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
        default_sizes = [63.0, 31.5, 16.0, 8.0, 4.0, 2.0, 1.0, 0.5, 0.25, 0.125, 0.063]
        cursor.execute('''
            INSERT OR IGNORE INTO sieve_sets (name, sizes, is_default)
            VALUES (?, ?, ?)
        ''', ('标准火山灰粒级', ','.join(map(str, default_sizes)), 1))


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


def add_sample(sample_no, sampling_site, eruption_layer, total_weight, description=""):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO samples (sample_no, sampling_site, eruption_layer, total_weight, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (sample_no, sampling_site, eruption_layer, total_weight, description))
        return cursor.lastrowid


def update_sample(sample_id, sample_no, sampling_site, eruption_layer, total_weight, description=""):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE samples 
            SET sample_no = ?, sampling_site = ?, eruption_layer = ?, 
                total_weight = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (sample_no, sampling_site, eruption_layer, total_weight, description, sample_id))
        return cursor.rowcount > 0


def delete_sample(sample_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sieve_data WHERE sample_id = ?', (sample_id,))
        cursor.execute('DELETE FROM samples WHERE id = ?', (sample_id,))
        return cursor.rowcount > 0


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
