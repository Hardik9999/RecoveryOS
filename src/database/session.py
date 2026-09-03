from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings

# engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False}) if using sqlite
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
