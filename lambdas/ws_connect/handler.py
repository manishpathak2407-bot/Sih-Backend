# 10Hz Dead Reckoning Backend Engine - SIH 2026
# AWS Amplify serverless migration: API Gateway WebSocket $connect route.
#
# PHASE 3 STUB (see AMPLIFY_MIGRATION.md): accepts every connection
# unconditionally, with no auth check and no connections_store registration
# yet. This exists only to prove out the WebSocket API's routing/integration
# wiring (amplify/custom/realtime-stack.ts) end-to-end via `ampx sandbox`
# before any real logic is layered in.
#
# Phase 4 replaces this body with:
#   - reading `token`/`device_id` from event["queryStringParameters"]
#   - verifying the JWT (ported from app/core/auth.py's authenticate_ws)
#   - rejecting the handshake (statusCode 401/403) on failure
#   - lambdas.common.connections_store.register_connection(connection_id, device_id)
#     on success — the direct replacement for today's
#     `active_connections[device_id] = websocket` in app/api/websocket.py.
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    connection_id = event.get("requestContext", {}).get("connectionId")
    logger.info("STUB $connect: accepting connectionId=%s with no auth check yet", connection_id)
    return {"statusCode": 200}
