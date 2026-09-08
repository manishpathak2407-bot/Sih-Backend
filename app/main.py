# 10Hz Dead Reckoning Backend Engine - SIH 2026
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.cache.redis_client import cache_manager
from app.db.database import init_db
from app.api.websocket import router as ws_router, queue_worker
from app.api.rest_routes import router as rest_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sih_backend")
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing SIH Dead Reckoning Backend...")
    await cache_manager.connect()
    await init_db()
    
    # Launch asynchronous queue processor worker
    worker_task = asyncio.create_task(queue_worker())
    logger.info("System ready. Ingestion queue worker active.")

    yield

    # Shutdown
    logger.info("Shutting down backend...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await cache_manager.disconnect()
    logger.info("Shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware to support development tools & dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API & WebSocket routes
app.include_router(ws_router)
app.include_router(rest_router)

@app.get("/")
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "docs": "/docs",
        "ws_endpoint": "/ws/track/{device_id}?token=<jwt>"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)

