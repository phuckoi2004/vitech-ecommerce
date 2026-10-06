from fastapi import FastAPI
from .database import test_database_connection

app = FastAPI(
    title="VieTech API",
    description="Backend API cho website bán hàng VieTech",
    version="1.0.0",
)


@app.get("/")
def root():
    return {
        "message": "VieTech API is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


@app.get("/health/db")
def database_health_check():
    try:
        result = test_database_connection()

        return {
            "status": "ok",
            "database": "connected",
            "test": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "database": "disconnected",
            "detail": str(e),
        }