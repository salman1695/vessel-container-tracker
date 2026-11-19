import re
from datetime import datetime, timezone
from typing import Optional
from app.db.connection import get_connection


def _normalize_severity(status: str, explicit_severity: Optional[str] = None) -> str:
    if explicit_severity:
        sev = explicit_severity.strip().upper()
        if sev in {"SUCCESS", "WARNING", "ERROR", "INFO"}:
            return sev

    st = (status or "").upper()
    if any(k in st for k in ["ERROR", "FAIL", "400", "401", "403", "404", "429", "500", "502", "504"]):
        return "ERROR"
    if any(k in st for k in ["WARN", "TIMEOUT", "NOT_FOUND", "SKIP", "STALE"]):
        return "WARNING"
    if any(k in st for k in ["SUCCESS", "HIT", "FOUND", "LIVE_FETCH", "FORCE_REFRESH", "ONLINE"]):
        return "SUCCESS"
    return "INFO"


def _clean_details(details: str) -> str:
    if not details:
        return ""
    # Agar detail mein raw URL aaye to usay clean readable message mein convert karein
    cleaned = re.sub(r"https?://\S+", "[Safecube API Endpoint]", details)
    return cleaned.strip()


def add_log(
    action_type: str,
    query_target: str,
    source: str,
    status: str,
    details: str,
    severity: Optional[str] = None
):
    resolved_severity = _normalize_severity(status, severity)
    cleaned_detail = _clean_details(details)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO activity_logs (timestamp, action_type, query_target, source, status, severity, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now(timezone.utc).isoformat(),
        action_type,
        query_target,
        source,
        status,
        resolved_severity,
        cleaned_detail
    ))
    conn.commit()
    conn.close()


def get_recent_logs(limit: int = 50, severity: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()

    if severity and severity.strip().upper() in {"SUCCESS", "WARNING", "ERROR", "INFO"}:
        cursor.execute(
            """
            SELECT id, timestamp, action_type, query_target, source, status, severity, details
            FROM activity_logs
            WHERE UPPER(severity) = ?
            ORDER BY id DESC LIMIT ?
            """,
            (severity.strip().upper(), limit)
        )
    else:
        cursor.execute(
            """
            SELECT id, timestamp, action_type, query_target, source, status, severity, details
            FROM activity_logs
            ORDER BY id DESC LIMIT ?
            """,
            (limit,)
        )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "action_type": r["action_type"],
            "query_target": r["query_target"],
            "source": r["source"],
            "status": r["status"],
            "severity": _normalize_severity(r["status"], r["severity"]),
            "details": r["details"],
        }
        for r in rows
    ]