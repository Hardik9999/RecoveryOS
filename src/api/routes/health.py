"""
Health check endpoint.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from src.api.dependencies import get_db

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Application health check",
    description="Returns the health status of the RecoveryOS API and its database connection."
)
def health_check(db: Session = Depends(get_db)):
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "service": "RecoveryOS"
    }
