"""FastAPI application entrypoint for the Zenith backend."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, models  # noqa: F401 (models import registers tables)
from .auth_routes import router as auth_router
from .database import Base, engine, ensure_schema
from .oauth_routes import router as oauth_router
from .search_routes import router as search_router

Base.metadata.create_all(bind=engine)
ensure_schema()

logger = logging.getLogger(__name__)

app = FastAPI(title="Zenith API")


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(search_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
