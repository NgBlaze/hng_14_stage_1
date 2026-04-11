from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from datetime import datetime, timezone
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": "Invalid input: name must be a string"},
        headers=CORS_HEADERS,
    )


@app.get("/api/classify")
async def classify_name(name: str = Query(default=None)):
    if not name or not name.strip():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Missing or empty name parameter"},
            headers=CORS_HEADERS,
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.genderize.io/", params={"name": name.strip()}
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": f"Upstream API error: {e.response.status_code}",
            },
            headers=CORS_HEADERS,
        )
    except httpx.RequestError:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": "Failed to reach upstream API"},
            headers=CORS_HEADERS,
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Internal server error"},
            headers=CORS_HEADERS,
        )

    gender = data.get("gender")
    sample_size = data.get("count", 0)

    if gender is None or sample_size == 0:
        return JSONResponse(
            status_code=200,
            content={
                "status": "error",
                "message": "No prediction available for the provided name",
            },
            headers=CORS_HEADERS,
        )

    probability = data.get("probability", 0.0)
    is_confident = bool(probability >= 0.7 and sample_size >= 100)
    processed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "data": {
                "name": data.get("name", name),
                "gender": gender,
                "probability": probability,
                "sample_size": sample_size,
                "is_confident": is_confident,
                "processed_at": processed_at,
            },
        },
        headers=CORS_HEADERS,
    )
