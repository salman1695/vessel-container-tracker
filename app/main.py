import asyncio
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.config import CACHE_TTL_HOURS
from app.db import (
    init_db,
    get_cached_shipment,
    save_shipment_to_db,
    search_by_vessel_name,
    get_tracking_history,
    get_stale_active_shipments,
    add_log,
    get_recent_logs,
)
from app.safecube import fetch_and_parse_shipment

app = FastAPI(
    title="Vessel & Container Tracker API",
    description="Modular Microservice for Container & Live Vessel Tracking with Audit Logs & Auto-Sync",
    version="2.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Frontend folder path setup
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def _extract_clean_error(exc: Exception) -> str:
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
    """Purani IN_TRANSIT shipments ko background mein Safecube API se fresh karta hai."""
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
                action_type="AUTO_SYNC",
                query_target=c_num,
                source="LIVE_API",
                status="SYNCED",
                severity="SUCCESS",
                details=f"Background auto-sync updated {c_num}"
            )
        except Exception as exc:
            failed_count += 1
            clean_err = _extract_clean_error(exc)
            sev = "WARNING" if "timeout" in clean_err.lower() else "ERROR"
            add_log(
                action_type="AUTO_SYNC",
                query_target=c_num,
                source="LIVE_API",
                status="FAILED",
                severity=sev,
                details=f"Auto-sync failed: {clean_err}"
            )

    return {
        "checked_stale": len(stale_list),
        "synced": synced_count,
        "failed": failed_count
    }


async def periodic_auto_sync_worker():
    """Har CACHE_TTL_HOURS ke baad automatically active shipments ko refresh karega."""
    while True:
        await asyncio.sleep(CACHE_TTL_HOURS * 3600)
        await asyncio.to_thread(sync_stale_shipments_job)


@app.on_event("startup")
async def startup_event():
    init_db()
    add_log(
        action_type="SYSTEM_START",
        query_target="SERVER",
        source="INTERNAL",
        status="ONLINE",
        severity="INFO",
        details="Application started & modular DB initialized"
    )
    asyncio.create_task(asyncio.to_thread(sync_stale_shipments_job))
    asyncio.create_task(periodic_auto_sync_worker())


@app.get("/", include_in_schema=False)
def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="frontend/index.html not found.")
    return FileResponse(index_path)


@app.get("/api/v1/health")
def health_check():
    return {"status": "online", "version": "2.2.0"}


@app.get("/api/v1/track")
def track_container(
    shipment_number: str = Query(..., description="Container Number or BL e.g. TCNU2686298"),
    sealine: Optional[str] = Query(None, description="Optional Carrier name or SCAC code e.g. COSCO or COSU"),
    force_refresh: bool = Query(False, description="If true, bypass cache and fetch live data")
):
    clean_num = shipment_number.strip().upper()

    # 1. Check valid cache unless force_refresh is True
    if not force_refresh:
        cached = get_cached_shipment(clean_num)
        if cached:
            add_log(
                action_type="CONTAINER_SEARCH",
                query_target=clean_num,
                source="CACHE",
                status="CACHE_HIT",
                severity="SUCCESS",
                details="Returned cached shipment (0 API credits used)"
            )
            return cached

    # 2. Fetch live from Safecube API & save to DB
    try:
        result = fetch_and_parse_shipment(clean_num, sealine)
        save_shipment_to_db(result)
        mode = "FORCE_REFRESH" if force_refresh else "LIVE_FETCH"
        add_log(
            action_type="CONTAINER_SEARCH",
            query_target=clean_num,
            source="LIVE_API",
            status=mode,
            severity="SUCCESS",
            details=f"Fetched live data ({result.get('detected_type')})"
        )
        return result
    except HTTPException as exc:
        sev = "WARNING" if exc.status_code in (404, 504) else "ERROR"
        add_log(
            action_type="CONTAINER_SEARCH",
            query_target=clean_num,
            source="LIVE_API",
            status=f"HTTP_{exc.status_code}",
            severity=sev,
            details=_extract_clean_error(exc)
        )
        raise


@app.get("/api/v1/vessel")
def track_vessel(
    name: str = Query(..., description="Vessel Name e.g. KMTC MUNDRA")
):
    clean_name = name.strip()
    matches = search_by_vessel_name(clean_name)

    if not matches:
        add_log(
            action_type="VESSEL_SEARCH",
            query_target=clean_name.upper(),
            source="DATABASE",
            status="NOT_FOUND",
            severity="WARNING",
            details=f"No tracked containers found for vessel '{clean_name.upper()}'"
        )
        raise HTTPException(
            status_code=404,
            detail=f"No tracked containers found on vessel '{clean_name}'. Pehle is vessel ka container track karein."
        )

    latest_record = matches[0]
    vessel_summary = latest_record.get("summary", {})

    # Sirf Vessel ke apne TRANSPORT / Voyage events (Cargo pickup/equipment events bilkul nahi)
    raw_vessel_events = latest_record.get("vessel_milestones") or []
    filtered_vessel_events = [
        ev for ev in raw_vessel_events
        if "PICKUP" not in (ev.get("description") or "").upper()
        and "DELIVER" not in (ev.get("description") or "").upper()
        and "AVAILABLE FOR PICKUP" not in (ev.get("description") or "").upper()
    ]

    add_log(
        action_type="VESSEL_SEARCH",
        query_target=vessel_summary.get("vessel_name") or clean_name.upper(),
        source="DATABASE",
        status="FOUND",
        severity="SUCCESS",
        details=f"Found {len(matches)} container(s) onboard"
    )

    return {
        "vessel_name": vessel_summary.get("vessel_name"),
        "vessel_imo": vessel_summary.get("vessel_imo"),
        "vessel_mmsi": vessel_summary.get("vessel_mmsi"),
        "vessel_call_sign": vessel_summary.get("vessel_call_sign"),
        "vessel_flag": vessel_summary.get("vessel_flag"),
        "voyage": vessel_summary.get("voyage"),
        "vessel_coordinates": vessel_summary.get("vessel_coordinates"),
        "ais_departure_port": vessel_summary.get("ais_departure_port"),
        "ais_arrival_port": vessel_summary.get("ais_arrival_port"),
        "sea_route_path": latest_record.get("sea_route_path", []),
        "vessel_milestones": filtered_vessel_events,
        "total_containers_tracked": len(matches),
        "containers": [m["summary"] for m in matches]
    }


@app.get("/api/v1/history")
def get_history(limit: int = Query(20, ge=1, le=100)):
    return {"history": get_tracking_history(limit)}


@app.get("/api/v1/logs")
def get_logs(
    limit: int = Query(50, ge=1, le=200),
    severity: Optional[str] = Query(None, description="Filter by SUCCESS, WARNING, ERROR, or INFO")
):
    return {"logs": get_recent_logs(limit=limit, severity=severity)}


@app.post("/api/v1/sync-active")
def trigger_manual_sync():
    """Tamam purani IN_TRANSIT shipments ko ek click par refresh karne ka endpoint."""
    summary = sync_stale_shipments_job()
    return {"message": "Active fleet sync completed", **summary}