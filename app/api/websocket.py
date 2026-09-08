import asyncio
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from app.core.auth import authenticate_ws
from app.core.time_sync import TimeSyncManager
from app.core.queue_manager import IngestionQueueManager
from app.fusion.kalman_filter import IMUKalmanFilter
from app.ml.ml_bridge import ml_bridge
from app.cache.redis_client import cache_manager
from app.db.database import AsyncSessionLocal
from app.db.crud import get_last_known_position, save_trajectory_point

logger = logging.getLogger(__name__)
router = APIRouter()

# Global Queue and Connection Pool
queue_mgr = IngestionQueueManager()
active_connections: Dict[str, WebSocket] = {}
device_kalman_filters: Dict[str, IMUKalmanFilter] = {}

async def restore_or_init_filter(device_id: str) -> IMUKalmanFilter:
    """
    Restores Kalman filter state from Redis, or falls back to TimescaleDB
    if Redis key expired (Problem 6), or creates new filter.
    """
    # 1. Try Redis
    cached_state = await cache_manager.get_live_device_state(device_id)
    if cached_state and "x" in cached_state and "P" in cached_state:
        logger.info(f"Restored Kalman filter for {device_id} from Redis.")
        return IMUKalmanFilter.from_state_dict(cached_state)

    # 2. Redis miss / expired: Query TimescaleDB
    async with AsyncSessionLocal() as session:
        last_pos = await get_last_known_position(session, device_id)
        if last_pos:
            logger.info(f"Restored Kalman filter for {device_id} from TimescaleDB (Redis TTL had expired).")
            kf = IMUKalmanFilter()
            kf.x[0, 0] = last_pos["x"]
            kf.x[1, 0] = last_pos["y"]
            kf.x[2, 0] = last_pos["z"]
            kf.x[3, 0] = last_pos["vx"]
            kf.x[4, 0] = last_pos["vy"]
            kf.x[5, 0] = last_pos["vz"]
            kf.x[6, 0] = last_pos["roll"]
            kf.x[7, 0] = last_pos["pitch"]
            kf.x[8, 0] = last_pos["yaw"]
            kf.last_timestamp = last_pos["timestamp"]
            return kf

    # 3. Fresh device session
    logger.info(f"Initialized brand-new Kalman filter state for {device_id}.")
    return IMUKalmanFilter()

@router.websocket("/ws/track/{device_id}")
async def websocket_track_endpoint(websocket: WebSocket, device_id: str):
    # Step 1: JWT Authentication during handshake
    authenticated_id = await authenticate_ws(websocket)
    if not authenticated_id:
        return

    # Check device_id match
    if authenticated_id != device_id and authenticated_id != "admin":
        logger.warning(f"Device ID mismatch: token sub={authenticated_id}, path={device_id}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Device ID mismatch")
        return

    await websocket.accept()
    active_connections[device_id] = websocket
    logger.info(f"WebSocket client connected: {device_id}")

    # Restore or create Kalman filter
    device_kalman_filters[device_id] = await restore_or_init_filter(device_id)

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "live")

            # 1. NTP Time Sync Request
            if msg_type == "time_sync":
                response = TimeSyncManager.process_sync_request(data)
                await websocket.send_text(json.dumps(response))
                continue

            # 2. Real-Time Live Frame (Priority 0)
            elif msg_type == "live":
                await queue_mgr.enqueue_live(device_id, data)

            # 3. Backlog Recovery Dump (Priority 1 with chunking)
            elif msg_type == "backlog":
                chunk = data.get("chunk", [])
                enqueued = await queue_mgr.enqueue_backlog_chunk(device_id, chunk)
                logger.info(f"Enqueued {enqueued} backlog frames for {device_id}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {device_id}")
    except Exception as e:
        logger.error(f"Error on WebSocket for {device_id}: {e}")
    finally:
        active_connections.pop(device_id, None)

async def queue_worker():
    """
    Background worker that continuously pulls from the Priority Ingestion Queue.
    Processes Live (P0) immediately, and Backlog (P1) cooperatively without blocking.
    """
    logger.info("Starting background Ingestion Queue Worker...")
    while True:
        item = await queue_mgr.get_next_item()
        try:
            device_id = item.device_id
            packet = item.data
            seq = item.seq_num
            is_backlog = item.is_backlog

            # 1. Retrieve or recover Kalman filter
            kf = device_kalman_filters.get(device_id)
            if not kf:
                kf = await restore_or_init_filter(device_id)
                device_kalman_filters[device_id] = kf

            # 2. Kalman Filter Fusion (Stage 1: Statistical)
            rough_state = kf.process_sample(packet)

            # 3. Add to sliding sensor window
            ml_bridge.add_sample(device_id, packet)

            # 4. ML Bridge Drift Correction (Stage 2: Learned Neural Correction)
            # Checks Redis window hash cache first -> O(1) hit if duplicate/backlog!
            drift_vector, is_cache_hit = await ml_bridge.get_drift_correction(device_id)

            # 5. Corrected True Position
            corrected_x = rough_state["x"] - float(drift_vector[0])
            corrected_y = rough_state["y"] - float(drift_vector[1])
            corrected_z = rough_state["z"] - float(drift_vector[2])

            payload_out = {
                "type": "position_update",
                "device_id": device_id,
                "seq": seq,
                "timestamp": item.timestamp,
                "x": round(corrected_x, 4),
                "y": round(corrected_y, 4),
                "z": round(corrected_z, 4),
                "vx": round(rough_state["vx"], 4),
                "vy": round(rough_state["vy"], 4),
                "vz": round(rough_state["vz"], 4),
                "yaw": round(rough_state["yaw"], 4),
                "is_backlog": is_backlog,
                "is_cache_hit": is_cache_hit,
                "is_verified": True
            }

            # 6. Push back to Flutter client if currently connected
            ws = active_connections.get(device_id)
            if ws:
                try:
                    await ws.send_text(json.dumps(payload_out))
                except Exception:
                    pass

            # 7. Update Redis Live Cache (1-hour TTL)
            state_dict = kf.to_state_dict()
            # Update state with latest corrected position
            state_dict["x"][0][0] = corrected_x
            state_dict["x"][1][0] = corrected_y
            state_dict["x"][2][0] = corrected_z
            await cache_manager.set_live_device_state(device_id, state_dict)

            # 8. Asynchronously persist to database
            async with AsyncSessionLocal() as session:
                await save_trajectory_point(session, payload_out)

        except Exception as e:
            logger.error(f"Error processing item in queue worker: {e}", exc_info=True)
        finally:
            queue_mgr.task_done()
