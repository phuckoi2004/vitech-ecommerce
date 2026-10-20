from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.env import database_url

# Development/test: backend/.env.local (never backend/.env); see app.core.env.
DATABASE_URL = database_url()


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_database_connection():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        return result.scalar()