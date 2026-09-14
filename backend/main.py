"""FastAPI application entrypoint for the Zenith backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, models  # noqa: F401 (models import registers tables)
from .auth_routes import router as auth_router
from .database import Base, engine
from .search_routes import router as search_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Zenith API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(search_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
