import re
from typing import Optional
import requests
from fastapi import HTTPException
from app.config import SINAY_API_KEY, BASE_URL, ENDPOINT
from app.carriers import resolve_sealine


def detect_shipment_type(number: str) -> str:
    # ISO Container format: 4 letters + 7 digits (e.g., TCNU2686298)
    if re.match(r"^[A-Z]{4}\d{7}$", number):
        return "CT"
    return "BL"


def _classify_event_stage(description: str, event_type: str) -> str:
    desc = (description or "").upper()
    if "GATE IN" in desc:
        return "GATE IN"
    if "GATE OUT" in desc:
        return "GATE OUT"
    if "EMPTY" in desc and "PICK" in desc:
        return "EMPTY PICKUP"
    if "LOAD" in desc:
        return "LOADED ON VESSEL"
    if "DISCHARG" in desc:
        return "DISCHARGED"
    if "DEPART" in desc or "SAIL" in desc:
        return "VESSEL DEPARTURE"
    if "ARRIV" in desc or "POD" in desc or "POL" in desc:
        return "PORT CALL"
    return event_type or "MILESTONE"


def fetch_and_parse_shipment(shipment_number: str, sealine: Optional[str] = None) -> dict:
    if not SINAY_API_KEY:
        raise HTTPException(status_code=500, detail="API Key missing in .env file.")

    clean_num = shipment_number.strip().upper()
    shipment_type = detect_shipment_type(clean_num)
    resolved_sealine = resolve_sealine(sealine)

    headers = {
        "Accept": "application/json",
        "API_KEY": SINAY_API_KEY,
    }

    params = {
        "shipmentNumber": clean_num,
        "shipmentType": shipment_type,
        "ais": "true",
        "route": "true",
    }

    if resolved_sealine:
        params["sealine"] = resolved_sealine

    try:
        response = requests.get(f"{BASE_URL}{ENDPOINT}", headers=headers, params=params, timeout=25)

        if response.status_code == 400:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid request parameters for '{clean_num}' (sealine={resolved_sealine or 'auto'})."
            )
        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid Safecube/Sinay API Key.")
        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"{shipment_type} '{clean_num}' not found. Try providing the shipping line name (e.g. COSCO, Maersk)."
            )
        if response.status_code == 429:
            raise HTTPException(status_code=429, detail="API rate limit or free quota exceeded.")

        response.raise_for_status()
        raw = response.json()

        metadata = raw.get("metadata") or {}
        vessels = raw.get("vessels") or []
        route = raw.get("route") or {}
        route_data = raw.get("routeData") or {}
        ais_info = (route_data.get("ais") or {}).get("data") or {}
        containers = raw.get("containers") or []

        current_vessel = vessels[-1] if vessels else {}
        container_obj = containers[0] if containers else {}

        sea_path = []
        for seg in route_data.get("routeSegments") or []:
            sea_path.extend(seg.get("path") or [])

        all_milestones = []
        container_milestones = []
        vessel_milestones = []
        latest_voyage = None

        for ev in (container_obj.get("events") or []):
            loc = ev.get("location") or {}
            fac = ev.get("facility") or {}
            ves = ev.get("vessel") or {}
            ev_type = (ev.get("eventType") or "").upper()
            voyage = ev.get("voyage")
            if voyage:
                latest_voyage = voyage
            
            parsed_ev = {
                "description": ev.get("description"),
                "event_code": ev.get("eventCode"),
                "event_type": ev_type,
                "location": loc.get("name"),
                "country": loc.get("country"),
                "facility": fac.get("name"),
                "date": ev.get("date"),
                "is_actual": ev.get("isActual"),
                "vessel": ves.get("name"),
                "voyage": voyage,
                "stage": _classify_event_stage(ev.get("description") or "", ev_type),
                "completion_status": "COMPLETED" if ev.get("isActual") else "PENDING",
            }

            all_milestones.append(parsed_ev)

            if ev_type == "EQUIPMENT":
                container_milestones.append(parsed_ev)
            elif ev_type == "TRANSPORT":
                vessel_milestones.append(parsed_ev)

        # Agar API ne explicitly eventType tag nahi diya to description se fallback classification
        if not container_milestones and not vessel_milestones and all_milestones:
            for item in all_milestones:
                desc_upper = (item.get("description") or "").upper()
                if any(k in desc_upper for k in ["VESSEL", "DEPARTURE", "ARRIVAL", "SAIL", "VOYAGE"]):
                    vessel_milestones.append(item)
                else:
                    container_milestones.append(item)

        return {
            "source": "LIVE_API",
            "detected_type": "Container (CT)" if shipment_type == "CT" else "Bill of Lading (BL)",
            "summary": {
                "container_number": metadata.get("shipmentNumber", clean_num),
                "container_size": container_obj.get("sizeType"),
                "shipping_line": metadata.get("sealineName") or metadata.get("sealine"),
                "status": metadata.get("shippingStatus"),
                "origin_port": ((route.get("pol") or {}).get("location") or {}).get("name"),
                "destination_port": ((route.get("pod") or {}).get("location") or {}).get("name"),
                "pol_date": (route.get("pol") or {}).get("date"),
                "eta": (route.get("pod") or {}).get("date"),
                "vessel_name": current_vessel.get("name"),
                "vessel_imo": current_vessel.get("imo"),
                "vessel_mmsi": current_vessel.get("mmsi"),
                "vessel_call_sign": current_vessel.get("callSign"),
                "vessel_flag": current_vessel.get("flag"),
                "voyage": latest_voyage,
                "vessel_coordinates": ais_info.get("lastVesselPosition"),
                "ais_departure_port": ais_info.get("departurePort"),
                "ais_arrival_port": ais_info.get("arrivalPort"),
            },
            "milestones": all_milestones,
            "container_milestones": container_milestones,
            "vessel_milestones": vessel_milestones,
            "sea_route_path": sea_path,
        }

    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Safecube API timed out.")
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Connection error: {str(exc)}")
