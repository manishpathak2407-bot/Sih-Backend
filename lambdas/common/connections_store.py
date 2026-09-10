# 10Hz Dead Reckoning Backend Engine - SIH 2026
# AWS Amplify serverless migration: WebSocket connection registry.
#
# Replaces app/api/websocket.py's module-level `active_connections: Dict[str,
# WebSocket]`. API Gateway WebSocket connections aren't Python objects you can
# hold onto across Lambda invocations — each connection is identified only by
# a `connectionId` string, and pushing a message to it later requires calling
# ApiGatewayManagementApi.post_to_connection(ConnectionId=...). This table is
# what makes that possible: it's the persistent map the in-memory dict used to
# be, keyed by connectionId (since $disconnect only ever receives a
# connectionId, not a device_id) with a GSI to look up the other direction.
#
# Table: Connections
#   PK (partition key) = connection_id
#   GSI "device_id-index": partition key = device_id
import time
from typing import Optional

from .dynamo import CONNECTIONS_TABLE_ENV, DEFAULT_CONNECTIONS_TABLE, get_table, to_dynamo

DEVICE_ID_INDEX = "device_id-index"


def _connections_table():
    return get_table(CONNECTIONS_TABLE_ENV, DEFAULT_CONNECTIONS_TABLE)


def register_connection(connection_id: str, device_id: str, table=None, connected_at: Optional[float] = None) -> None:
    """Called from the $connect Lambda once auth succeeds — the direct
    replacement for `active_connections[device_id] = websocket`. `connected_at`
    doubles as the GSI's range key (see module docstring) so
    get_connection_for_device() can deterministically pick the most recent
    connection; defaults to now() and only needs overriding in tests that
    register multiple connections for one device faster than the clock's
    resolution."""
    table = table or _connections_table()
    table.put_item(
        Item={
            "connection_id": connection_id,
            "device_id": device_id,
            "connected_at": to_dynamo(connected_at if connected_at is not None else time.time()),
        }
    )


def unregister_connection(connection_id: str, table=None) -> None:
    """Called from the $disconnect Lambda — the direct replacement for
    `active_connections.pop(device_id, None)`. Note (matching today's
    behavior, see app/api/websocket.py's finally block): only the connection
    entry is removed here. The device's EKF state in state_store is
    deliberately left untouched, so backlog processing / a reconnect can
    still resume it."""
    table = table or _connections_table()
    table.delete_item(Key={"connection_id": connection_id})


def get_device_for_connection(connection_id: str, table=None) -> Optional[str]:
    """Used by the $disconnect Lambda if it needs to know which device a
    closing connection belonged to before removing it."""
    table = table or _connections_table()
    response = table.get_item(Key={"connection_id": connection_id})
    item = response.get("Item")
    return item.get("device_id") if item else None


def get_connection_for_device(device_id: str, table=None) -> Optional[str]:
    """Used by the live-path and backlog-consumer Lambdas to find where to
    `post_to_connection` a position_update reply for a device — the direct
    replacement for reading `active_connections.get(device_id)`. Returns None
    if the device has no open connection right now (mirrors today's "send
    only if currently connected" behavior); queries the GSI since this table
    is keyed by connection_id, not device_id.
    """
    table = table or _connections_table()
    response = table.query(
        IndexName=DEVICE_ID_INDEX,
        KeyConditionExpression="device_id = :device_id",
        ExpressionAttributeValues={":device_id": device_id},
        Limit=1,
        ScanIndexForward=False,
    )
    items = response.get("Items", [])
    return items[0]["connection_id"] if items else None
