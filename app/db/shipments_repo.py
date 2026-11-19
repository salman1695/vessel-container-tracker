import json
from datetime import datetime, timedelta, timezone
from app.config import CACHE_TTL_HOURS
from app.db.connection import get_connection


def get_cached_shipment(container_number: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT clean_data, updated_at, status FROM shipments WHERE container_number = ?",
        (container_number.upper(),)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    clean_data_str = row["clean_data"]
    updated_at_str = row["updated_at"]
    status = row["status"]
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

    conn = get_connection()
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT container_number, vessel_name, shipping_line, status, updated_at FROM shipments ORDER BY updated_at DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "container_number": r["container_number"],
            "vessel_name": r["vessel_name"],
            "shipping_line": r["shipping_line"],
            "status": r["status"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def get_stale_active_shipments():
    """Un active (non-DELIVERED) containers ko nikalta hai jinhein update hue CACHE_TTL_HOURS se zyada ho chuka hai."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT container_number, shipping_line, updated_at FROM shipments WHERE UPPER(COALESCE(status, '')) != 'DELIVERED'"
    )
    rows = cursor.fetchall()
    conn.close()

    stale = []
    now = datetime.now(timezone.utc)
    for r in rows:
        container_num = r["container_number"]
        shipping_line = r["shipping_line"]
        updated_at_str = r["updated_at"]
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
            if now - updated_at >= timedelta(hours=CACHE_TTL_HOURS):
                stale.append({"container_number": container_num, "shipping_line": shipping_line})
        except (ValueError, TypeError):
            stale.append({"container_number": container_num, "shipping_line": shipping_line})
    return stale


def search_by_vessel_name(vessel_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT clean_data FROM shipments WHERE LOWER(vessel_name) LIKE ?",
        (f"%{vessel_name.strip().lower()}%",)
    )
    rows = cursor.fetchall()
    conn.close()
    return [json.loads(r["clean_data"]) for r in rows]

def delete_shipment_from_db(container_number: str) -> bool:
    """Database se shipment record delete karta hai taake agli search LIVE API se aaye."""
    clean_num = container_number.strip().upper()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM shipments WHERE container_number = ?", (clean_num,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted