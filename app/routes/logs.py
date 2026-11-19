from typing import Optional
from fastapi import APIRouter, Query
from app.db import get_recent_logs
from app.services import sync_stale_shipments_job

router = APIRouter(prefix="/api/v1", tags=["Audit Logs & Sync"])


@router.get("/logs")
def get_logs(
    limit: int = Query(100, ge=1, le=200),
    severity: Optional[str] = Query(None, description="Filter by SUCCESS, WARNING, ERROR, or INFO")
):
    return {"logs": get_recent_logs(limit=limit, severity=severity)}


@router.post("/sync-active")
def trigger_manual_sync():
    summary = sync_stale_shipments_job()
    return {"message": "Active fleet sync completed", **summary}