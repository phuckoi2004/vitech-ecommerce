from fastapi import FastAPI

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