from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from api.database import init_db
from api.routes.profiles import router as profiles_router

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

# ─── DB init ──────────────────────────────────────────────────────────────────

init_db()

# ─── Exception handlers ──────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": "Invalid query parameters"},
        headers=CORS_HEADERS,
    )

# ─── Routes ───────────────────────────────────────────────────────────────────

app.include_router(profiles_router)
