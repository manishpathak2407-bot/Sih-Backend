# 10Hz Dead Reckoning Backend Engine - SIH 2026
# AWS Amplify serverless migration: trajectory (position history) store.
#
# Replaces app/db/crud.py + app/db/models.py's TrajectoryPoint/TimescaleDB
# table. Every query in the original crud.py is single-table, no-join,
# partition-by-device + range-by-time — DynamoDB's native access pattern — and
# no TimescaleDB-specific feature (hypertable compression, time_bucket(),
# continuous aggregates) is used anywhere in the codebase, so this is a
# straight port, not a feature-for-feature reimplementation of anything SQL.
#
# Table: DeviceTelemetry (same table as state_store.py's STATE items)
#   PK = "DEVICE#{device_id}"
#   SK = "TRAJ#{iso8601_timestamp}#{seq}"   (the #{seq} suffix disambiguates
#        same-timestamp collisions, which backlog chunks can produce when
#        multiple packets share a coarse timestamp)
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .dynamo import DEVICE_TELEMETRY_TABLE_ENV, DEFAULT_DEVICE_TELEMETRY_TABLE, get_table, to_dynamo, from_dynamo

TRAJ_PREFIX = "TRAJ#"


def _device_telemetry_table():
    return get_table(DEVICE_TELEMETRY_TABLE_ENV, DEFAULT_DEVICE_TELEMETRY_TABLE)


def _pk(device_id: str) -> str:
    return f"DEVICE#{device_id}"


def _traj_sort_key(timestamp: float, seq: Any) -> str:
    """Zero-padded ISO-8601-ish timestamp keeps SK lexicographically sortable
    (DynamoDB sort keys compare as strings), with the sequence number (or a
    short random suffix, if no seq was supplied) breaking ties between items
    that share a timestamp."""
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp else datetime.now(timezone.utc)
    seq_part = seq if seq not in (None, "") else uuid.uuid4().hex[:8]
    return f"{TRAJ_PREFIX}{dt.isoformat()}#{seq_part}"


def _point_item(point_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build a DynamoDB item from a point dict shaped like the payload the
    websocket/REST handlers already build (same keys save_trajectory_point()
    accepted in the old crud.py: device_id, timestamp, x/y/z, vx/vy/vz,
    roll/pitch/yaw, movement_state, step_count, is_backlog, is_verified,
    covariance, raw_sensor, session_id, seq)."""
    device_id = point_data["device_id"]
    timestamp = point_data.get("timestamp") or 0.0
    item = {
        "PK": _pk(device_id),
        "SK": _traj_sort_key(timestamp, point_data.get("seq")),
        "device_id": device_id,
        "session_id": point_data.get("session_id", "default"),
        "seq_num": point_data.get("seq", 0),
        "time": timestamp,
        "x": point_data.get("x", 0.0),
        "y": point_data.get("y", 0.0),
        "z": point_data.get("z", 0.0),
        "vx": point_data.get("vx", 0.0),
        "vy": point_data.get("vy", 0.0),
        "vz": point_data.get("vz", 0.0),
        "roll": point_data.get("roll", 0.0),
        "pitch": point_data.get("pitch", 0.0),
        "yaw": point_data.get("yaw", 0.0),
        "movement_state": point_data.get("movement_state", "REST"),
        "step_count": point_data.get("step_count", 0),
        "is_backlog": bool(point_data.get("is_backlog", False)),
        "is_verified": bool(point_data.get("is_verified", True)),
    }
    if point_data.get("covariance") is not None:
        item["covariance"] = point_data["covariance"]
    if point_data.get("raw_sensor") is not None:
        item["raw_sensor"] = point_data["raw_sensor"]
    return to_dynamo(item)


def save_trajectory_point(point_data: Dict[str, Any], table=None) -> Dict[str, Any]:
    """Insert a single verified trajectory point. Direct replacement for
    app/db/crud.py's save_trajectory_point()."""
    table = table or _device_telemetry_table()
    item = _point_item(point_data)
    table.put_item(Item=item)
    return from_dynamo(item)


def save_trajectory_batch(points_data: List[Dict[str, Any]], table=None) -> int:
    """Bulk-insert a backlog chunk. Direct replacement for
    app/db/crud.py's save_trajectory_batch(); uses BatchWriteItem via the
    resource-level batch_writer(), which handles the 25-item-per-request
    limit and retries under-the-hood, mirroring the old single-commit bulk
    insert's all-or-nothing feel closely enough for this use case."""
    if not points_data:
        return 0
    table = table or _device_telemetry_table()
    with table.batch_writer() as batch:
        for point_data in points_data:
            batch.put_item(Item=_point_item(point_data))
    return len(points_data)


def get_trajectory_history(device_id: str, limit: int = 500, table=None) -> List[Dict[str, Any]]:
    """Fetch recent trajectory history for a device, oldest first. Direct
    replacement for app/db/crud.py's get_trajectory_history()."""
    table = table or _device_telemetry_table()
    response = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
        ExpressionAttributeValues={":pk": _pk(device_id), ":prefix": TRAJ_PREFIX},
        ScanIndexForward=True,
        Limit=limit,
    )
    return [from_dynamo(item) for item in response.get("Items", [])]


def get_last_known_position(device_id: str, table=None) -> Optional[Dict[str, Any]]:
    """Fallback for when a device has no STATE item at all (e.g. its first
    packet ever, or a state_store item that was somehow lost) — query the
    most recent trajectory point instead. Direct replacement for
    app/db/crud.py's get_last_known_position(), which served the same role as
    the Redis-TTL-expiry fallback in the old two-tier cache design; here it's
    simply "no STATE item yet" since there's only one store now."""
    table = table or _device_telemetry_table()
    response = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
        ExpressionAttributeValues={":pk": _pk(device_id), ":prefix": TRAJ_PREFIX},
        ScanIndexForward=False,
        Limit=1,
    )
    items = response.get("Items", [])
    if not items:
        return None
    return from_dynamo(items[0])
