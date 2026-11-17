import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )
    yield
    await app.state.redis.aclose()


app = FastAPI(
    title="BarVision API Gateway",
    version="1.0.0",
    description="Event-Driven Multimodal Smart Bar & Cocktail Search Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"service": "BarVision API Gateway", "status": "online", "version": "1.0.0"}


@app.get("/health")
async def health():
    """Liveness: process is up."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready(request: Request):
    """Readiness: dependencies reachable."""
    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        return JSONResponse({"status": "not_ready", "redis": str(exc)}, status_code=503)
    return {"status": "ready"}