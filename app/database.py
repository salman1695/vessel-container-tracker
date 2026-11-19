import sqlite3
import json
from datetime import datetime, timedelta, timezone
from app.config import CACHE_TTL_HOURS

DB_PATH = "tracking_cache.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Existing Shipments Table (Same schema so existing data never breaks)
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

    # 2. New Audit & Activity Logs Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            action_type TEXT,
            query_target TEXT,
            source TEXT,
            status TEXT,
            details TEXT
        )
    """)

    conn.commit()
    conn.close()


def add_log(action_type: str, query_target: str, source: str, status: str, details: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO activity_logs (timestamp, action_type, query_target, source, status, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        datetime.now(timezone.utc).isoformat(),
        action_type,
        query_target,
        source,
        status,
        details
    ))
    conn.commit()
    conn.close()


def get_recent_logs(limit: int = 30):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, timestamp, action_type, query_target, source, status, details FROM activity_logs ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "timestamp": r[1],
            "action_type": r[2],
            "query_target": r[3],
            "source": r[4],
            "status": r[5],
            "details": r[6],
        }
        for r in rows
    ]


def get_cached_shipment(container_number: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT clean_data, updated_at, status FROM shipments WHERE container_number = ?",
        (container_number.upper(),)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    clean_data_str, updated_at_str, status = row
    updated_at = datetime.fromisoformat(updated_at_str)

    # Delivered shipments permanently cached (0 wasted credits), active shipments follow CACHE_TTL_HOURS
    is_delivered = (status or "").upper() == "DELIVERED"
    is_fresh = (datetime.now(timezone.utc) - updated_at) < timedelta(hours=CACHE_TTL_HOURS)

    if is_delivered or is_fresh:
        data = json.loads(clean_data_str)
        data["source"] = "CACHE (0 API Credits Used)"
        data["last_synced_at"] = updated_at_str
        return data

    return None


def save_shipment_to_db(clean_data: dict):
    summary = clean_data.get("summary", {})
    now_iso = datetime.now(timezone.utc).isoformat()
    clean_data["last_synced_at"] = now_iso

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO shipments 
        (container_number, vessel_name, vessel_imo, shipping_line, status, clean_data, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        summary.get("container_number"),
        summary.get("vessel_name"),
        str(summary.get("vessel_imo") or ""),
        summary.get("shipping_line"),
        summary.get("status"),
        json.dumps(clean_data),
        now_iso
    ))
    conn.commit()
    conn.close()


def get_tracking_history(limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT container_number, vessel_name, shipping_line, status, updated_at FROM shipments ORDER BY updated_at DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "container_number": r[0],
            "vessel_name": r[1],
            "shipping_line": r[2],
            "status": r[3],
            "updated_at": r[4],
        }
        for r in rows
    ]


def get_stale_active_shipments():
    """Un active (non-DELIVERED) containers ko nikalta hai jinhein update hue CACHE_TTL_HOURS se zyada ho chuka hai."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT container_number, shipping_line, updated_at FROM shipments WHERE UPPER(COALESCE(status, '')) != 'DELIVERED'"
    )
    rows = cursor.fetchall()
    conn.close()

    stale = []
    now = datetime.now(timezone.utc)
    for container_num, shipping_line, updated_at_str in rows:
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
            if now - updated_at >= timedelta(hours=CACHE_TTL_HOURS):
                stale.append({"container_number": container_num, "shipping_line": shipping_line})
        except ValueError:
            stale.append({"container_number": container_num, "shipping_line": shipping_line})
    return stale


def search_by_vessel_name(vessel_name: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT clean_data FROM shipments WHERE LOWER(vessel_name) LIKE ?",
        (f"%{vessel_name.strip().lower()}%",)
    )
    rows = cursor.fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]