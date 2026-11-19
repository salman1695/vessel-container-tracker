import sqlite3
from pathlib import Path

# Project root ke mutabiq tracking_cache.db ka exact path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = str(BASE_DIR / "tracking_cache.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Shipments & Vessels Cache Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            container_number TEXT PRIMARY KEY,
            vessel_name TEXT,
            vessel_imo TEXT,
            shipping_line TEXT,
            status TEXT,
            clean_data TEXT,
            updated_at TEXT
        )
    """)

    # 2. System Activity & API Audit Logs Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            action_type TEXT,
            query_target TEXT,
            source TEXT,
            status TEXT,
            severity TEXT DEFAULT 'INFO',
            details TEXT
        )
    """)

    # Backward compatibility: agar purani activity_logs table mein severity column na ho to add kar do
    cursor.execute("PRAGMA table_info(activity_logs)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    if "severity" not in existing_cols:
        cursor.execute("ALTER TABLE activity_logs ADD COLUMN severity TEXT DEFAULT 'INFO'")

    conn.commit()
    conn.close()