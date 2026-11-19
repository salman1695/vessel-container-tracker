
# Sync & Error Helper Module)
from fastapi import HTTPException
from app.db import (
    add_log,
    get_stale_active_shipments,
    save_shipment_to_db,
)
from app.safecube import fetch_and_parse_shipment


def extract_clean_error(exc: Exception) -> str:
    """Long URLs ya raw tracebacks ke bajaye clean readable error message nikalta hai."""
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    msg = str(exc)
    if "400" in msg:
        return "Bad Request (400): Invalid carrier code or shipment parameters"
    if "401" in msg:
        return "Unauthorized (401): Invalid API Key"
    if "404" in msg:
        return "Not Found (404): Shipment record not found"
    if "429" in msg:
        return "Rate Limit (429): API quota exceeded"
    if "timed out" in msg.lower() or "timeout" in msg.lower():
        return "Timeout: Safecube API took too long to respond"
    return msg[:160]


def sync_stale_shipments_job() -> dict:
    """Sirf manual Sync Fleet click par chalne wala sync job (no background auto-sync)."""
    stale_list = get_stale_active_shipments()
    synced_count = 0
    failed_count = 0

    for item in stale_list:
        c_num = item["container_number"]
        s_line = item.get("shipping_line")
        try:
            fresh_data = fetch_and_parse_shipment(c_num, s_line)
            save_shipment_to_db(fresh_data)
            synced_count += 1
            add_log(
                action_type="MANUAL_SYNC",
                query_target=c_num,
                source="LIVE_API",
                status="SYNCED",
                severity="SUCCESS",
                details=f"Synced {c_num} from live API"
            )
        except Exception as exc:
            failed_count += 1
            clean_err = extract_clean_error(exc)
            add_log(
                action_type="MANUAL_SYNC",
                query_target=c_num,
                source="LIVE_API",
                status="FAILED",
                severity="ERROR",
                details=f"Sync failed: {clean_err}"
            )

    return {
        "checked_stale": len(stale_list),
        "synced": synced_count,
        "failed": failed_count
    }