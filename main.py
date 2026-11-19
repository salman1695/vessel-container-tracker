import os
from typing import Optional
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Dono env names support kar rahe hain taake .env mein koi bhi ho chal jaye
SINAY_API_KEY = os.getenv("SINAY_API_KEY") or os.getenv("SAFECUBE_API_KEY")
BASE_URL = "https://api.sinay.ai"
ENDPOINT = "/container-tracking/api/v2/shipment"

app = FastAPI(
    title="Vessel & Container Tracker API",
    description="Track containers and live vessel details using Safecube (Sinay) API",
    version="1.0.0"
)

# To connectFrontend (React / HTML) 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"status": "online", "message": "Welcome to Vessel & Container Tracker!"}


@app.get("/api/v1/track")
def track_container(
    shipment_number: str = Query(..., description="Container Number e.g. TCNU2686298"),
    sealine: Optional[str] = Query(None, description="Optional Carrier SCAC code e.g. COSU")
):
    if not SINAY_API_KEY:   
        raise HTTPException(status_code=500, detail="API Key missing in .env file.")

    headers = {
        "Accept": "application/json",
        "API_KEY": SINAY_API_KEY,
    }

 
    params = {
        "shipmentNumber": shipment_number.strip().upper(),
        "shipmentType": "CT",
        "ais": "true",
        "route": "true",
    }

    # Agar user ne sealine diya hai tabhi add karein, warna Safecube auto-detect karega
    if sealine and sealine.strip():
        params["sealine"] = sealine.strip().upper()

    try:
        response = requests.get(
            f"{BASE_URL}{ENDPOINT}",
            headers=headers,
            params=params,
            timeout=25,
        )

        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid or unauthorized Safecube/Sinay API Key.")

        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Container not found or invalid container number.")

        if response.status_code == 429:
            raise HTTPException(status_code=429, detail="API rate limit or free shipment quota exceeded.")

        response.raise_for_status()

        if not response.text.strip():
            raise HTTPException(status_code=404, detail="Server returned empty response for this container.")

        raw_data = response.json()

        # Safecube response mein se Vessel aur Main Details safely extract karna
        metadata = raw_data.get("metadata", {}) or {}
        vessels = raw_data.get("vessels", []) or []
        locations = raw_data.get("locations", []) or []
        route = raw_data.get("route", {}) or {}
        ais_data = raw_data.get("ais", {}) or {}

        # Latest/Current vessel nikalna
        current_vessel = vessels[-1] if vessels else {}

        return {
            "summary": {
                "container_number": metadata.get("shipmentNumber", shipment_number.upper()),
                "shipping_line": metadata.get("sealineName") or metadata.get("sealine"),
                "status": metadata.get("shippingStatus"),
                "vessel_name": current_vessel.get("name"),
                "vessel_imo": current_vessel.get("imo"),
                "vessel_mmsi": current_vessel.get("mmsi"),
                "vessel_coordinates": ais_data.get("lastVesselPosition") or current_vessel.get("position"),
                "eta": route.get("pod", {}).get("date") if isinstance(route.get("pod"), dict) else None,
            },
            "raw_data": raw_data  # Poora response bhi sath bhej rahe hain debugging aur milestones ke liye
        }

    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Safecube API request timed out.")
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to connect to tracking provider: {str(exc)}")