"""
DRISHTI Backend — FastAPI entrypoint (Phase 2).

Implements only the Phase 1 MVP Core API (docs/API_CONTRACT.md):
  GET  /api/health
  GET  /api/regions
  POST /api/simulation
  GET  /api/simulation/{scenario_id}
  GET  /api/risk-zones

The Later Implementation endpoints (/api/flood/{event_id}, /api/response-plan,
/api/route) are intentionally NOT wired up yet — they depend on modules owned
by Engineers 2 and 4 (see docs/API_CONTRACT.md "Implementation Priority").
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api import health, regions, simulation, risk
from backend.app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="DRISHTI API",
    description="AI-powered disaster-management decision-support platform — Flood MVP (Phase 2 infrastructure)",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    """
    Flattens every error response to docs/API_CONTRACT.md's locked shape:
    `{ "error": "..." }`. Route handlers raise HTTPException(detail=<string>);
    FastAPI's default would otherwise wrap that as `{"detail": "..."}`.
    """
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": message})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Also flattens Pydantic/FastAPI request-validation errors (422) to the same
    `{ "error": "..." }` shape, so every error response — not just the ones
    raised manually via HTTPException — matches docs/API_CONTRACT.md.
    """
    first_error = exc.errors()[0] if exc.errors() else {"msg": "Invalid request."}
    field = ".".join(str(p) for p in first_error.get("loc", []) if p != "body")
    message = f"{field}: {first_error.get('msg')}" if field else first_error.get("msg")
    return JSONResponse(status_code=422, content={"error": message})


app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(regions.router, prefix="/api", tags=["regions"])
app.include_router(simulation.router, prefix="/api", tags=["simulation"])
app.include_router(risk.router, prefix="/api", tags=["risk"])


@app.get("/")
def root():
    return {"service": "DRISHTI API", "docs": "/docs", "health": "/api/health"}
