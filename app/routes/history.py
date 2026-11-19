from fastapi import APIRouter, HTTPException, Query
from app.db import add_log, delete_shipment_from_db, get_tracking_history

router = APIRouter(prefix="/api/v1", tags=["History"])


@router.get("/history")
def get_history(limit: int = Query(50, ge=1, le=100)):
    return {"history": get_tracking_history(limit)}


@router.delete("/history/{container_number}")
def delete_history_item(container_number: str):
    clean_num = container_number.strip().upper()
    deleted = delete_shipment_from_db(clean_num)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Shipment '{clean_num}' not found in database.")

    add_log(
        action_type="HISTORY_DELETE",
        query_target=clean_num,
        source="DATABASE",
        status="DELETED",
        severity="INFO",
        details=f"Removed '{clean_num}' from cache; next search will fetch LIVE data"
    )
    return {"message": f"Deleted {clean_num} from database", "container_number": clean_num}