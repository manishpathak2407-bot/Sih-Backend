# 10Hz Dead Reckoning Backend Engine - SIH 2026
# AWS Amplify serverless migration: shared DynamoDB helpers.
#
# See AMPLIFY_MIGRATION.md for the overall architecture. This module holds the
# low-level bits shared by state_store.py / trajectory_store.py /
# connections_store.py so those files stay focused on their own access
# patterns: boto3 resource/table lookup (by env var, so tests can point at a
# moto-mocked table without touching real AWS) and float<->Decimal conversion
# (DynamoDB's Number type has no native float — boto3's resource API requires
# Decimal for anything written, and hands Decimal back on read).
import os
from decimal import Decimal
from functools import lru_cache
from typing import Any

import boto3

# Table name env vars — populated by the CDK stack (amplify/custom/realtime-stack.ts)
# at deploy time. Defaults match what a local moto/LocalStack test setup would use.
DEVICE_TELEMETRY_TABLE_ENV = "DEVICE_TELEMETRY_TABLE"
CONNECTIONS_TABLE_ENV = "CONNECTIONS_TABLE"

DEFAULT_DEVICE_TELEMETRY_TABLE = "DeviceTelemetry"
DEFAULT_CONNECTIONS_TABLE = "Connections"


@lru_cache()
def _resource():
    """A cached boto3 DynamoDB resource. Lambda cold starts pay for this once
    per execution environment; warm invocations reuse it, mirroring the
    connection-pool-at-module-scope pattern the FastAPI app used for asyncpg."""
    return boto3.resource("dynamodb")


def get_table(name_env_var: str, default_name: str):
    """Look up a DynamoDB Table resource by the table name in the given env
    var, falling back to `default_name` if unset. Kept as a thin function
    (not resolved at import time) so tests can set the env var / patch boto3's
    resource *before* calling into store functions, after moto's mock is active."""
    table_name = os.environ.get(name_env_var, default_name)
    return _resource().Table(table_name)


def to_dynamo(value: Any) -> Any:
    """Recursively convert floats (and containers of them) to Decimal so the
    value is writable via boto3's DynamoDB resource API. Leaves other types
    (str, int, bool, None) untouched."""
    if isinstance(value, float):
        # str() first avoids the binary-float-to-Decimal precision artifacts
        # you get from Decimal(0.1) directly (Decimal('0.1000000000000000055511151231257827021181583404541015625')).
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_dynamo(v) for v in value]
    return value


def from_dynamo(value: Any) -> Any:
    """The inverse of to_dynamo(): recursively convert Decimal back to float
    (or int, if the Decimal has no fractional part — e.g. step_count) so
    values coming back from DynamoDB behave like the plain JSON-derived types
    the rest of the codebase (IMUKalmanFilter.from_state_dict, etc.) expects."""
    if isinstance(value, Decimal):
        as_int = int(value)
        return as_int if as_int == value else float(value)
    if isinstance(value, dict):
        return {k: from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_dynamo(v) for v in value]
    return value
