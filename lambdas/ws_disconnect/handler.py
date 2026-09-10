# 10Hz Dead Reckoning Backend Engine - SIH 2026
# AWS Amplify serverless migration: API Gateway WebSocket $disconnect route.
#
# PHASE 3 STUB (see AMPLIFY_MIGRATION.md): no-op, does not touch
# connections_store yet. API Gateway invokes $disconnect on a best-effort
# basis (it is not guaranteed to fire for every disconnect, e.g. on an
# abrupt network drop), matching the "best-effort cleanup" nature of today's
# `finally: active_connections.pop(device_id, None)` in app/api/websocket.py.
#
# Phase 4 replaces this body with:
#   lambdas.common.connections_store.unregister_connection(connection_id)
# Per that module's docstring, this must NOT touch the device's EKF state in
# state_store — only the connection entry is removed, so backlog processing
# or a reconnect can still resume the device's filter state.
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    connection_id = event.get("requestContext", {}).get("connectionId")
    logger.info("STUB $disconnect: connectionId=%s (no connections_store cleanup yet)", connection_id)
    return {"statusCode": 200}
