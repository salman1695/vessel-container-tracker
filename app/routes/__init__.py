from app.routes.history import router as history_router
from app.routes.logs import router as logs_router
from app.routes.tracking import router as tracking_router

__all__ = ["tracking_router", "history_router", "logs_router"]