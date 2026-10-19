import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .core.config import get_auth_settings
from .core.dependencies import get_runtime
from .core.errors import AuthError
from .database import test_database_connection
from .routers import (
    auth,
    catalog,
    chat,
    content,
    internal,
    orders,
    payments,
    promotions,
    purchasing,
    reviews,
    service_requests,
    statistics,
    users,
    webhooks,
    wishlist_cart,
)
from .routers.admin import users as admin_users
from .routers.dependencies import get_return_policy
from .routers.errors import service_error_handler
from .services.exceptions import ServiceError
from .services.internal_jobs import database_error_code

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail at startup, not on the first login: validates settings and connects the state store.
    app.dependency_overrides.get(get_runtime, get_runtime)()
    # Same for business settings read per request (an invalid RETURN_WINDOW_DAYS raises ValueError here).
    app.dependency_overrides.get(get_return_policy, get_return_policy)()
    yield


app = FastAPI(title="VieTech API", description="Backend API cho website bán hàng VieTech", version="1.1.0",
              lifespan=lifespan)
# One validated source for CORS and the CSRF Origin check (production requires HTTPS, no "*").
cors_origins = [origin for origin in get_auth_settings().cors_origins if origin != "*"]
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"])
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin_users.router)

# Stage 6 business APIs: public/customer routers, then /admin routers (Staff/Admin only).
for module in (catalog, wishlist_cart, orders, payments, promotions, reviews, chat, service_requests, content):
    app.include_router(module.router)
for module in (catalog, orders, payments, promotions, purchasing, reviews, chat, service_requests, content,
               statistics):
    app.include_router(module.admin_router)
# Machine-to-machine entry points: SePay webhook (HMAC; 503 until SEPAY_* is configured) and cron jobs
# (shared secret; 503 until INTERNAL_CRON_SECRET is configured).
app.include_router(webhooks.router)
app.include_router(internal.router)


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, error: AuthError):
    return JSONResponse(status_code=error.status_code, content={"detail": error.message}, headers=error.headers)


# Business errors from Stage 4 services become 4xx/502 responses instead of 500.
app.add_exception_handler(ServiceError, service_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, error: RequestValidationError):
    # Default validation output may echo a password/OTP input.
    safe_errors = [{"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]} for item in error.errors()]
    return JSONResponse(status_code=422, content={"detail": safe_errors})


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, error: SQLAlchemyError):
    # Type and SQLSTATE only: the error text may hold SQL parameters or connection details. Path without query string.
    logger.error("Database error on %s %s: %s sqlstate=%s", request.method, request.url.path, type(error).__name__,
                 database_error_code(error))
    return JSONResponse(status_code=503, content={"detail": "Không thể xử lý dữ liệu lúc này. Vui lòng thử lại"})


@app.middleware("http")
async def prevent_auth_caching(request: Request, call_next):
    response = await call_next(request)
    # Personal and internal data must not be cached by browsers or proxies.
    private_paths = ("/auth", "/users", "/admin", "/internal", "/webhooks")
    if request.url.path.startswith(private_paths) or "authorization" in request.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def root():
    return {"message": "VieTech API is running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
def database_health_check():
    try:
        result = test_database_connection()
        return {"status": "ok", "database": "connected", "test": result}
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "error", "database": "disconnected"})
