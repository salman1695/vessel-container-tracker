from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.db import add_log, init_db
from app.routes import history_router, logs_router, tracking_router

app = FastAPI(
    title="Vessel & Container Tracker API",
    description="Modular Microservice for Container & Live Vessel Tracking",
    version="2.4.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.on_event("startup")
def startup_event():
    init_db()
    add_log(
        action_type="SYSTEM_START",
        query_target="SERVER",
        source="INTERNAL",
        status="ONLINE",
        severity="INFO",
        details="Application started & modular DB initialized"
    )


@app.get("/", include_in_schema=False)
def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="frontend/index.html not found.")
    return FileResponse(index_path)


app.include_router(tracking_router)
app.include_router(history_router)
app.include_router(logs_router)