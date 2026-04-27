import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from api.database import init_db
from api.limiter import limiter
from api.routes.auth import router as auth_router
from api.routes.profiles import router as profiles_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="Insighta Labs+ API")
app.state.limiter = limiter

# ─── CORS ─────────────────────────────────────────────────────────────────────

_allowed_origins = [
    "https://hng-14-web-portal.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
]
_env_portal = os.environ.get("WEB_PORTAL_URL", "").strip().rstrip("/")
if _env_portal and _env_portal not in _allowed_origins:
    _allowed_origins.append(_env_portal)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Version", "X-CSRF-Token"],
    allow_credentials=True,
)

# ─── DB init ──────────────────────────────────────────────────────────────────

init_db()

# ─── Logging middleware ───────────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    logger.info("%s %s %s %.1fms", request.method, request.url.path, response.status_code, ms)
    return response

# ─── Exception handlers ──────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"status": "error", "message": "Invalid query parameters"})


@app.exception_handler(HTTPException)
async def http_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "message": exc.detail})


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"status": "error", "message": "Rate limit exceeded. Please try again later."},
    )

# ─── Routes ───────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(profiles_router)
