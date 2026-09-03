"""
FastAPI dependency injection for the RecoveryOS API layer.
"""
from sqlalchemy.orm import Session
from src.database.session import SessionLocal


def get_db():
    """
    Yield a database session per-request and ensure it is closed afterward.
    Uses the existing SessionLocal factory from Phase 1.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
