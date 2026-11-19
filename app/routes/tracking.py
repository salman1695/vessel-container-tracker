from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.db import (
    add_log,
    get_cached_shipment,
    save_shipment_to_db,
    search_by_vessel_name,
)
from app.safecube import fetch_and_parse_shipment
from app.services import extract_clean_error

router = APIRouter(prefix="/api/v1", tags=["Tracking"])


@router.get("/health")
def health_check():
    return {"status": "online", "version": "2.4.0"}


@router.get("/track")
def track_container(
    shipment_number: str = Query(..., description="Container Number or BL e.g. TCNU2686298"),
    sealine: Optional[str] = Query(None, description="Optional Carrier name or SCAC code e.g. COSCO or COSU"),
    force_refresh: bool = Query(False, description="If true, bypass cache and fetch live data")
):
    clean_num = shipment_number.strip().upper()

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
            details=extract_clean_error(exc)
        )
        raise


@router.get("/vessel")
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