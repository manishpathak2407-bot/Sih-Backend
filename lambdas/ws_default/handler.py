# 10Hz Dead Reckoning Backend Engine - SIH 2026
# AWS Amplify serverless migration: API Gateway WebSocket $default route.
#
# PHASE 3 STUB (see AMPLIFY_MIGRATION.md): does not dispatch on message
# `type` yet, does not touch state_store/trajectory_store, and does not
# enqueue anything to SQS. It only echoes the received body back over the
# same connection via ApiGatewayManagementApi.post_to_connection() — this is
# deliberately here (rather than a bare no-op like the connect/disconnect
# stubs) because proving out `post_to_connection` end-to-end, including its
# IAM permissions and the management-API endpoint construction from
# event["requestContext"], is exactly the mechanism Phase 5's real `live`/
# `time_sync` fast path depends on. Getting it working now, with a trivial
# echo, de-risks that dependency before real business logic is layered in.
#
# Phase 5 replaces this body with the real dispatch on `type`:
#   - "time_sync"  -> TimeSyncManager.process_sync_request() (ported verbatim
#                     from app/core/time_sync.py), reply immediately
#   - "live"       -> state_store.get_device_state() -> kf.process_sample()
#                     -> state_store.put_device_state() (with
#                     require_newer_than) + trajectory_store.save_trajectory_point()
#                     -> post_to_connection() with the position_update
#   - "backlog"    -> published to the SQS FIFO queue (MessageGroupId=device_id)
#                     for backlog_consumer to drain (Phase 6), not processed
#                     inline
import json
import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _reply(request_context: dict, payload: dict) -> None:
    domain = request_context["domainName"]
    stage = request_context["stage"]
    connection_id = request_context["connectionId"]
    endpoint_url = f"https://{domain}/{stage}"
    client = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint_url)
    client.post_to_connection(ConnectionId=connection_id, Data=json.dumps(payload).encode("utf-8"))


def handler(event, context):
    request_context = event.get("requestContext", {})
    connection_id = request_context.get("connectionId")

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        logger.warning("STUB $default: connectionId=%s sent invalid JSON, ignoring", connection_id)
        return {"statusCode": 200}

    logger.info("STUB $default: connectionId=%s type=%s (echoing, no real processing yet)",
                connection_id, body.get("type"))

    try:
        _reply(request_context, {"type": "stub_echo", "received": body})
    except Exception:
        # Matches today's "best-effort push, don't crash the loop if the
        # client is already gone" tolerance in app/api/websocket.py's
        # queue_worker() — a send failure here shouldn't fail the invocation.
        logger.exception("STUB $default: post_to_connection failed for connectionId=%s", connection_id)

    return {"statusCode": 200}
