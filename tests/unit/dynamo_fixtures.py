# 10Hz Dead Reckoning Backend Engine - SIH 2026
# Shared moto-backed DynamoDB table fixtures for tests/unit/test_*_store.py.
import boto3

from lambdas.common.dynamo import DEFAULT_CONNECTIONS_TABLE, DEFAULT_DEVICE_TELEMETRY_TABLE


def create_device_telemetry_table(region_name: str = "us-east-1"):
    """Create the DeviceTelemetry table (PK/SK single-table design, see
    lambdas/common/state_store.py and trajectory_store.py docstrings) against
    whatever DynamoDB endpoint boto3 currently resolves to — a moto mock, in
    every caller of this helper today."""
    client = boto3.client("dynamodb", region_name=region_name)
    client.create_table(
        TableName=DEFAULT_DEVICE_TELEMETRY_TABLE,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return boto3.resource("dynamodb", region_name=region_name).Table(DEFAULT_DEVICE_TELEMETRY_TABLE)


def create_connections_table(region_name: str = "us-east-1"):
    """Create the Connections table with its device_id-index GSI (see
    lambdas/common/connections_store.py docstring)."""
    client = boto3.client("dynamodb", region_name=region_name)
    client.create_table(
        TableName=DEFAULT_CONNECTIONS_TABLE,
        KeySchema=[{"AttributeName": "connection_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "connection_id", "AttributeType": "S"},
            {"AttributeName": "device_id", "AttributeType": "S"},
            {"AttributeName": "connected_at", "AttributeType": "N"},
        ],
        GlobalSecondaryIndexes=[
            {
                # connected_at as the GSI's range key is what makes "most
                # recent connection for this device" well-defined — a
                # partition-key-only GSI query has no ordering guarantee.
                "IndexName": "device_id-index",
                "KeySchema": [
                    {"AttributeName": "device_id", "KeyType": "HASH"},
                    {"AttributeName": "connected_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
            }
        ],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    )
    return boto3.resource("dynamodb", region_name=region_name).Table(DEFAULT_CONNECTIONS_TABLE)
