# 10Hz Dead Reckoning Backend Engine - SIH 2026
# AWS Amplify serverless migration: per-device Kalman filter state store.
#
# Replaces app/cache/redis_client.py's `device:state:{device_id}` key (and the
# two-tier Redis-then-Postgres fallback in app/api/websocket.py's
# restore_or_init_filter()) with a single DynamoDB item per device. See
# AMPLIFY_MIGRATION.md section "Persistence" for the schema rationale: every
# access pattern here is a single-item get/put keyed by device_id, which is
# exactly DynamoDB's native shape — no cache-then-DB fallback tier is needed
# once there's only one store.
#
# Table: DeviceTelemetry
#   PK = "DEVICE#{device_id}"
#   SK = "STATE"
# Item shape mirrors IMUKalmanFilter.to_state_dict()/from_state_dict() exactly
# (x, P, last_timestamp, movement_state, step_count, accel_history,
# last_step_time), plus `updated_at` and `pending_mode` (used by the
# redefined POST /device/{id}/mode endpoint — see AMPLIFY_MIGRATION.md).
import time
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError

from .dynamo import DEVICE_TELEMETRY_TABLE_ENV, DEFAULT_DEVICE_TELEMETRY_TABLE, get_table, to_dynamo, from_dynamo

STATE_SORT_KEY = "STATE"


def _device_telemetry_table():
    return get_table(DEVICE_TELEMETRY_TABLE_ENV, DEFAULT_DEVICE_TELEMETRY_TABLE)


def _pk(device_id: str) -> str:
    return f"DEVICE#{device_id}"


def get_device_state(device_id: str, table=None) -> Optional[Dict[str, Any]]:
    """Fetch the live EKF state dict for a device, or None if it has never
    been persisted (brand-new device). The returned dict is directly
    compatible with IMUKalmanFilter.from_state_dict()."""
    table = table or _device_telemetry_table()
    response = table.get_item(Key={"PK": _pk(device_id), "SK": STATE_SORT_KEY})
    item = response.get("Item")
    if not item:
        return None
    state = from_dynamo(item)
    state.pop("PK", None)
    state.pop("SK", None)
    state.pop("updated_at", None)
    return state


def put_device_state(
    device_id: str,
    state_dict: Dict[str, Any],
    table=None,
    require_newer_than: Optional[float] = None,
) -> bool:
    """Persist a device's EKF state dict (as produced by
    IMUKalmanFilter.to_state_dict()).

    `require_newer_than`, when given, adds a conditional-write guard: the
    write is rejected unless the item doesn't exist yet, or its stored
    `last_timestamp` is strictly less than `require_newer_than` (or absent).
    This is the safeguard called out in AMPLIFY_MIGRATION.md section
    "Ordering/backlog" — without it, a live-path invocation and a
    backlog-consumer invocation racing on the same device could overwrite
    each other's state out of order, silently corrupting the filter. Returns
    False (instead of raising) when the condition fails, so callers can
    decide whether to retry from a fresh read or drop the stale write.
    """
    table = table or _device_telemetry_table()
    item = to_dynamo(dict(state_dict))
    item["PK"] = _pk(device_id)
    item["SK"] = STATE_SORT_KEY
    item["updated_at"] = to_dynamo(time.time())

    put_kwargs: Dict[str, Any] = {"Item": item}
    if require_newer_than is not None:
        put_kwargs["ConditionExpression"] = (
            "attribute_not_exists(PK) OR attribute_not_exists(last_timestamp) "
            "OR last_timestamp < :new_ts"
        )
        put_kwargs["ExpressionAttributeValues"] = {":new_ts": to_dynamo(require_newer_than)}

    try:
        table.put_item(**put_kwargs)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def set_pending_mode(device_id: str, mode: str, table=None) -> None:
    """Redefined POST /device/{device_id}/mode semantics (see
    AMPLIFY_MIGRATION.md): rather than mutating a live in-memory filter object
    (impossible once there's no persistent process), write the desired mode
    onto the STATE item. The next `live` packet processed for this device
    picks it up and clears it (see consume_pending_mode()). This means the
    mode change is always applied eventually rather than silently no-op'ing
    when no connection happens to be open — a behavioral improvement over the
    original endpoint, but a real semantic change to flag to API consumers.
    """
    table = table or _device_telemetry_table()
    table.update_item(
        Key={"PK": _pk(device_id), "SK": STATE_SORT_KEY},
        UpdateExpression="SET pending_mode = :mode, updated_at = :now",
        ExpressionAttributeValues={":mode": mode, ":now": to_dynamo(time.time())},
    )


def consume_pending_mode(device_id: str, table=None) -> Optional[str]:
    """Read and clear any pending_mode set by set_pending_mode(), for the
    live-path Lambda to apply on the next packet it processes for this
    device. Returns None if no mode override is pending."""
    table = table or _device_telemetry_table()
    response = table.update_item(
        Key={"PK": _pk(device_id), "SK": STATE_SORT_KEY},
        UpdateExpression="REMOVE pending_mode",
        ReturnValues="UPDATED_OLD",
    )
    old = response.get("Attributes", {})
    return old.get("pending_mode")
