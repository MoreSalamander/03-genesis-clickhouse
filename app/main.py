"""Genesis OS — Institutional Intelligence API.

Run:  .venv/bin/uvicorn app.main:app --port 8020
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings

app = FastAPI(title="Genesis OS — Institutional Intelligence", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/healthz")
@app.get("/status")
def health() -> dict:  # /status alias: Cloud Run's GFE reserves /healthz
    return {"ok": True, "banner": settings.banner()}


@app.on_event("startup")
def startup() -> None:
    from app.observability.tracing import setup_tracing
    from app.workflows.runtime import get_runtime

    setup_tracing(settings, "genesis-institutional-api")
    runtime = get_runtime()
    print(f"[api] {settings.banner()}")
    registered = runtime.datahub.bootstrap()
    if registered:
        print(f"[api] DataHub: {registered} ClickHouse tables registered as datasets")
