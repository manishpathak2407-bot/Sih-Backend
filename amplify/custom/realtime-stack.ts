// 10Hz Dead Reckoning Backend Engine - SIH 2026
// AWS Amplify serverless migration: the custom CDK stack for everything the
// device-facing realtime path needs. See AMPLIFY_MIGRATION.md for the
// architecture rationale. This is NOT an Amplify-managed category (no
// defineAuth/defineData) — Amplify Gen 2's documented escape hatch for
// "custom AWS resources living alongside an Amplify app" is exactly a plain
// CDK Stack obtained via `backend.createStack(name)`, which is what
// amplify/backend.ts hands into createRealtimeStack() below.
//
// PHASE 3 (current): provisions the DynamoDB tables, the SQS FIFO backlog
// queue, and the WebSocket API wired to STUB Lambda handlers (see the
// PHASE 3 STUB comments in lambdas/ws_connect, ws_disconnect, ws_default,
// backlog_consumer) — enough to deploy via `npx ampx sandbox` and confirm
// the plumbing (routes, integrations, IAM, event-source-mapping) works
// end-to-end before any real business logic lands in Phases 4-6.
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Duration, RemovalPolicy } from 'aws-cdk-lib';
import type { Stack } from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { SqsEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { WebSocketApi, WebSocketStage } from 'aws-cdk-lib/aws-apigatewayv2';
import { WebSocketLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { CfnOutput } from 'aws-cdk-lib';

// amplify/custom/ files run as ESM (see amplify/package.json's "type":
// "module"), so __dirname isn't available directly — this is the standard
// ESM equivalent, matching the pattern Amplify's own generated function
// resources use internally.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..', '..');
const LAMBDAS_DIR = path.join(REPO_ROOT, 'lambdas');

// Table/queue name env vars, matching lambdas/common/dynamo.py's
// DEVICE_TELEMETRY_TABLE_ENV / CONNECTIONS_TABLE_ENV constants exactly —
// keep these two lists in sync if either side changes.
const DEVICE_TELEMETRY_TABLE_ENV = 'DEVICE_TELEMETRY_TABLE';
const CONNECTIONS_TABLE_ENV = 'CONNECTIONS_TABLE';
const BACKLOG_QUEUE_URL_ENV = 'BACKLOG_QUEUE_URL';

export function createRealtimeStack(stack: Stack) {
  // --- DynamoDB tables (see lambdas/common/state_store.py and
  // trajectory_store.py docstrings for the single-table PK/SK design) ---
  const deviceTelemetryTable = new dynamodb.Table(stack, 'DeviceTelemetryTable', {
    tableName: 'DeviceTelemetry',
    partitionKey: { name: 'PK', type: dynamodb.AttributeType.STRING },
    sortKey: { name: 'SK', type: dynamodb.AttributeType.STRING },
    billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    removalPolicy: RemovalPolicy.RETAIN,
  });

  // See lambdas/common/connections_store.py docstring: connected_at as the
  // GSI's range key is what makes "most recent connection for this device"
  // well-defined (a partition-key-only GSI query has no ordering guarantee).
  const connectionsTable = new dynamodb.Table(stack, 'ConnectionsTable', {
    tableName: 'Connections',
    partitionKey: { name: 'connection_id', type: dynamodb.AttributeType.STRING },
    billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    removalPolicy: RemovalPolicy.DESTROY, // pure ephemeral connection state, safe to drop on stack teardown
  });
  connectionsTable.addGlobalSecondaryIndex({
    indexName: 'device_id-index',
    partitionKey: { name: 'device_id', type: dynamodb.AttributeType.STRING },
    sortKey: { name: 'connected_at', type: dynamodb.AttributeType.NUMBER },
  });

  // --- SQS FIFO backlog queue (see AMPLIFY_MIGRATION.md "Ordering/backlog")
  // ---
  // MessageGroupId = device_id on every publish (set by the ws_default and
  // rest_sensor_data Lambdas in Phase 6) is what reproduces today's
  // per-device strict ordering guarantee without a shared process-wide
  // priority queue: FIFO guarantees in-order delivery *within* a group,
  // while different devices' groups drain independently/concurrently.
  const backlogDeadLetterQueue = new sqs.Queue(stack, 'DeviceBacklogDLQ', {
    queueName: 'sih-device-backlog-dlq.fifo',
    fifo: true,
  });
  const backlogQueue = new sqs.Queue(stack, 'DeviceBacklogQueue', {
    queueName: 'sih-device-backlog.fifo',
    fifo: true,
    contentBasedDeduplication: false, // callers set an explicit MessageDeduplicationId (device_id:seq_start:seq_end)
    visibilityTimeout: Duration.seconds(60),
    deadLetterQueue: { queue: backlogDeadLetterQueue, maxReceiveCount: 5 },
  });

  // --- Lambda functions ---
  // PHASE 3 stubs (see each handler.py's module docstring for what Phase
  // 4/5/6 replaces them with). Python 3.12 to match the existing app/'s
  // Python 3.11+ codebase; bumped one minor version since 3.12 is the
  // current Lambda-supported runtime closest to it.
  // Left untyped (not `: Partial<lambda.FunctionProps>`) so `runtime` stays
  // inferred as the concrete `lambda.Runtime` type rather than
  // `Runtime | undefined` — Partial<> would make every spread-in field
  // optional, which FunctionProps' required `runtime` then rejects.
  const commonPythonProps = {
    runtime: lambda.Runtime.PYTHON_3_12,
    timeout: Duration.seconds(10),
    memorySize: 256,
  };

  const wsConnectFn = new lambda.Function(stack, 'WsConnectFunction', {
    ...commonPythonProps,
    functionName: 'sih-ws-connect',
    code: lambda.Code.fromAsset(path.join(LAMBDAS_DIR, 'ws_connect')),
    handler: 'handler.handler',
    environment: { [CONNECTIONS_TABLE_ENV]: connectionsTable.tableName },
  });

  const wsDisconnectFn = new lambda.Function(stack, 'WsDisconnectFunction', {
    ...commonPythonProps,
    functionName: 'sih-ws-disconnect',
    code: lambda.Code.fromAsset(path.join(LAMBDAS_DIR, 'ws_disconnect')),
    handler: 'handler.handler',
    environment: { [CONNECTIONS_TABLE_ENV]: connectionsTable.tableName },
  });

  const wsDefaultFn = new lambda.Function(stack, 'WsDefaultFunction', {
    ...commonPythonProps,
    functionName: 'sih-ws-default',
    timeout: Duration.seconds(15), // live-path processing budget, see AMPLIFY_MIGRATION.md latency notes
    code: lambda.Code.fromAsset(path.join(LAMBDAS_DIR, 'ws_default')),
    handler: 'handler.handler',
    environment: {
      [DEVICE_TELEMETRY_TABLE_ENV]: deviceTelemetryTable.tableName,
      [CONNECTIONS_TABLE_ENV]: connectionsTable.tableName,
      [BACKLOG_QUEUE_URL_ENV]: backlogQueue.queueUrl,
    },
  });

  const backlogConsumerFn = new lambda.Function(stack, 'BacklogConsumerFunction', {
    ...commonPythonProps,
    functionName: 'sih-backlog-consumer',
    timeout: Duration.seconds(30),
    code: lambda.Code.fromAsset(path.join(LAMBDAS_DIR, 'backlog_consumer')),
    handler: 'handler.handler',
    environment: {
      [DEVICE_TELEMETRY_TABLE_ENV]: deviceTelemetryTable.tableName,
      [CONNECTIONS_TABLE_ENV]: connectionsTable.tableName,
    },
  });
  backlogConsumerFn.addEventSource(
    new SqsEventSource(backlogQueue, { batchSize: 10, reportBatchItemFailures: true })
  );

  // --- IAM: least-privilege table/queue access per function ---
  connectionsTable.grantReadWriteData(wsConnectFn);
  connectionsTable.grantReadWriteData(wsDisconnectFn);
  deviceTelemetryTable.grantReadWriteData(wsDefaultFn);
  connectionsTable.grantReadData(wsDefaultFn); // to resolve device_id -> connectionId for replies
  backlogQueue.grantSendMessages(wsDefaultFn);
  deviceTelemetryTable.grantReadWriteData(backlogConsumerFn);
  connectionsTable.grantReadData(backlogConsumerFn);

  // --- WebSocket API ---
  const webSocketApi = new WebSocketApi(stack, 'SihRealtimeWebSocketApi', {
    apiName: 'sih-dead-reckoning-realtime',
    connectRouteOptions: { integration: new WebSocketLambdaIntegration('ConnectIntegration', wsConnectFn) },
    disconnectRouteOptions: { integration: new WebSocketLambdaIntegration('DisconnectIntegration', wsDisconnectFn) },
    defaultRouteOptions: { integration: new WebSocketLambdaIntegration('DefaultIntegration', wsDefaultFn) },
  });

  const stage = new WebSocketStage(stack, 'SihRealtimeStage', {
    webSocketApi,
    stageName: 'prod',
    autoDeploy: true,
  });

  // post_to_connection (ApiGatewayManagementApi) requires this grant — the
  // direct replacement for today's implicit ability to call
  // `websocket.send_text()` on a held-open connection object.
  stage.grantManagementApiAccess(wsDefaultFn);
  stage.grantManagementApiAccess(backlogConsumerFn);

  new CfnOutput(stack, 'WebSocketUrl', { value: stage.url });
  new CfnOutput(stack, 'DeviceTelemetryTableName', { value: deviceTelemetryTable.tableName });
  new CfnOutput(stack, 'ConnectionsTableName', { value: connectionsTable.tableName });
  new CfnOutput(stack, 'BacklogQueueUrl', { value: backlogQueue.queueUrl });

  return {
    deviceTelemetryTable,
    connectionsTable,
    backlogQueue,
    backlogDeadLetterQueue,
    wsConnectFn,
    wsDisconnectFn,
    wsDefaultFn,
    backlogConsumerFn,
    webSocketApi,
    stage,
  };
}
