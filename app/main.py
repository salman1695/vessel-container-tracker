import asyncio
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.config import CACHE_TTL_HOURS
from app.database import (
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
    version="2.1.0"
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
            add_log("AUTO_SYNC", c_num, "LIVE_API", "SUCCESS", f"Background auto-sync updated {c_num}")
        except Exception as exc:
            failed_count += 1
            add_log("AUTO_SYNC", c_num, "LIVE_API", "ERROR", f"Auto-sync failed: {str(exc)}")

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
    add_log("SYSTEM_START", "SERVER", "INTERNAL", "ONLINE", "Application started & database initialized")
    # Startup par stale active shipments ko non-blocking background mein refresh karein
    asyncio.create_task(asyncio.to_thread(sync_stale_shipments_job))
    # Periodic background loop start karein
    asyncio.create_task(periodic_auto_sync_worker())


@app.get("/", include_in_schema=False)
def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="frontend/index.html not found.")
    return FileResponse(index_path)


@app.get("/api/v1/health")
def health_check():
    return {"status": "online", "version": "2.1.0"}


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
            add_log("CONTAINER_SEARCH", clean_num, "CACHE", "HIT", "Returned cached shipment (0 API credits used)")
            return cached

    # 2. Fetch live from Safecube API & save to DB
    try:
        result = fetch_and_parse_shipment(clean_num, sealine)
        save_shipment_to_db(result)
        mode = "FORCE_REFRESH" if force_refresh else "LIVE_FETCH"
        add_log("CONTAINER_SEARCH", clean_num, "LIVE_API", mode, f"Fetched live data ({result.get('detected_type')})")
        return result
    except HTTPException as exc:
        add_log("CONTAINER_SEARCH", clean_num, "LIVE_API", f"ERROR_{exc.status_code}", str(exc.detail))
        raise


@app.get("/api/v1/vessel")
def track_vessel(
    name: str = Query(..., description="Vessel Name e.g. KMTC MUNDRA")
):
    clean_name = name.strip()
    matches = search_by_vessel_name(clean_name)

    if not matches:
        add_log("VESSEL_SEARCH", clean_name.upper(), "DATABASE", "NOT_FOUND", "No tracked containers on this vessel")
        raise HTTPException(
            status_code=404,
            detail=f"No tracked containers found on vessel '{clean_name}'. Pehle is vessel ka container track karein."
        )

    latest_record = matches[0]
    vessel_summary = latest_record.get("summary", {})
    add_log("VESSEL_SEARCH", vessel_summary.get("vessel_name") or clean_name.upper(), "DATABASE", "FOUND", f"Found {len(matches)} container(s) onboard")

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
        # Sirf Vessel ke apne TRANSPORT events (Container EQUIPMENT events se alag)
        "vessel_milestones": latest_record.get("vessel_milestones") or latest_record.get("milestones", []),
        "total_containers_tracked": len(matches),
        "containers": [m["summary"] for m in matches]
    }


@app.get("/api/v1/history")
def get_history(limit: int = Query(15, ge=1, le=50)):
    return {"history": get_tracking_history(limit)}


@app.get("/api/v1/logs")
def get_logs(limit: int = Query(30, ge=1, le=100)):
    return {"logs": get_recent_logs(limit)}


@app.post("/api/v1/sync-active")
def trigger_manual_sync():
    """Tamam purani IN_TRANSIT shipments ko ek click par refresh karne ka endpoint."""
    summary = sync_stale_shipments_job()
    return {"message": "Active fleet sync completed", **summary}