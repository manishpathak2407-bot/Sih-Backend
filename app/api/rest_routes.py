# 10Hz Dead Reckoning Backend Engine - SIH 2026
from typing import List, Optional
from datetime import timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db_session
from app.core.auth import create_access_token
from app.cache.redis_client import cache_manager
from app.api.websocket import queue_mgr, active_connections
from app.db.crud import get_trajectory_history

router = APIRouter()

class TokenRequest(BaseModel):
    device_id: str = Field(..., description="Unique hardware or app UUID")
    expires_minutes: Optional[int] = Field(default=60 * 24 * 7, description="Token lifetime in minutes")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    device_id: str
    expires_in_seconds: int

class SensorPacketSchema(BaseModel):
    seq: int
    timestamp: float
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    mx: Optional[float] = None
    my: Optional[float] = None
    mz: Optional[float] = None

class BatchUploadRequest(BaseModel):
    device_id: str
    packets: List[SensorPacketSchema]

@router.post("/auth/token", response_model=TokenResponse, summary="Mint JWT token for a device")
async def generate_device_token(req: TokenRequest):
    """Generates an authentication token for WebSocket handshake."""
    token = create_access_token(
        data={"sub": req.device_id, "device_id": req.device_id},
        expires_delta=timedelta(minutes=req.expires_minutes)
    )
    return TokenResponse(
        access_token=token,
        device_id=req.device_id,
        expires_in_seconds=req.expires_minutes * 60
    )

@router.post("/sensor-data", summary="Fallback REST batch upload endpoint")
async def upload_batch_sensor_data(req: BatchUploadRequest):
    """
    REST fallback when WebSockets are blocked by proxies or firewalls.
    Enqueues batch to the priority queue as backlog.
    """
    packets_dict = [p.model_dump() for p in req.packets]
    enqueued = await queue_mgr.enqueue_backlog_chunk(req.device_id, packets_dict)
    return {
        "status": "enqueued",
        "device_id": req.device_id,
        "count": enqueued,
        "queue_size": queue_mgr.queue_size
    }

@router.get("/health", summary="System healthcheck and live status")
async def health_check():
    """Returns status of cache layer, queues, and active connections."""
    return {
        "status": "healthy",
        "redis_connected": cache_manager.is_redis_connected,
        "active_websockets": len(active_connections),
        "queue_depth": queue_mgr.queue_size
    }

@router.get("/device/{device_id}/trajectory", summary="Fetch stored trajectory history")
async def get_device_trajectory(
    device_id: str,
    limit: int = 500,
    db: AsyncSession = Depends(get_db_session)
):
    """Returns chronological trajectory points from TimescaleDB/SQLite."""
    points = await get_trajectory_history(db, device_id, limit=limit)
    return [
        {
            "seq": p.seq_num,
            "timestamp": p.time.timestamp(),
            "x": p.x,
            "y": p.y,
            "z": p.z,
            "vx": p.vx,
            "vy": p.vy,
            "vz": p.vz,
            "roll": p.roll,
            "pitch": p.pitch,
            "yaw": p.yaw,
            "is_backlog": p.is_backlog,
            "is_verified": p.is_verified
        }
        for p in points
    ]

