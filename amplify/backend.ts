// 10Hz Dead Reckoning Backend Engine - SIH 2026
// AWS Amplify Gen 2 backend entrypoint.
//
// This project deliberately defines no Amplify-managed categories (no
// defineAuth, no defineData/AppSync) — see AMPLIFY_MIGRATION.md sections
// "Realtime transport" and "Auth" for why: the device-facing protocol is a
// custom JSON-over-WebSocket contract best served by a plain API Gateway
// WebSocket API, and auth is the existing self-issued JWT scheme rather than
// Cognito. `defineBackend({})` with an empty resource map plus a custom CDK
// stack (via `backend.createStack`) is Amplify Gen 2's documented pattern
// for exactly this situation.
import { defineBackend } from '@aws-amplify/backend';
import { createRealtimeStack } from './custom/realtime-stack';

const backend = defineBackend({});

const realtimeStack = backend.createStack('SihRealtimeStack');
createRealtimeStack(realtimeStack);
