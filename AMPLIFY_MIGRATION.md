# Migrating Sih-Backend to AWS Amplify (Serverless Rewrite)

## Context

This service is a 10Hz pedestrian dead-reckoning backend: FastAPI + a native WebSocket
server + an in-process Extended Kalman Filter (EKF) + Redis + TimescaleDB, currently
deployed via Docker on EC2/Render (see [DEPLOYMENT.md](DEPLOYMENT.md)). We're migrating it
to run on **AWS Amplify**. Amplify has no way to run a persistent process or a native
WebSocket server — it only hosts Lambda functions and AppSync GraphQL — so this is a real
architectural rewrite, not a lift-and-shift.

## Status

| Phase | What | Status |
|---|---|---|
| 1 | Kalman filter state-fix (`accel_history`/`last_step_time`/covariance round-trip) | ✅ done ([c5d5b78](../../commit/c5d5b78)) |
| 2 | DynamoDB data-access layer (`lambdas/common/{state,trajectory,connections}_store.py`) | ✅ done ([5408bf3](../../commit/5408bf3)) |
| 3 | Amplify Gen 2 scaffold + custom CDK realtime stack, stub Lambda integrations | ✅ code complete, **not yet deployed** (no AWS credentials connected — see below) |
| 4 | Auth Lambdas (JWT mint/verify, Secrets Manager for `SECRET_KEY`) | not started |
| 5 | `ws_default` live fast-path (real `time_sync`/`live` processing) | not started |
| 6 | SQS FIFO backlog path + `/sensor-data` | not started |
| 7 | Remaining REST reads, redefined `/health` and `/device/{id}/mode` | not started |
| 8 | Mobile client validation, promoted-branch smoke tests, decommission old deploy paths | not started |

**Phase 3 could not be deployed in this environment**: `npx ampx sandbox` requires real AWS
credentials, which aren't connected here. What *has* been verified without needing them:
TypeScript compiles cleanly (`tsc --noEmit`), and the CDK stack synthesizes to a valid
CloudFormation template (`cdk.App().synth()`, which needs no AWS account access) producing
the exact expected resources — 2 DynamoDB tables, 2 SQS queues (+ DLQ), 4 Lambda functions,
a WebSocket API with 3 routes/integrations, and the SQS→Lambda event source mapping. Actual
deployment (`npm run sandbox`) and the "confirm it accepts connections" smoke test are the
remaining step once AWS credentials are available.

## Recommended architecture

- **Realtime transport: API Gateway WebSocket API** (`$connect`/`$disconnect`/`$default`
  routes, each backed by a Lambda), wired into the Amplify Gen 2 project via a custom CDK
  construct ([amplify/custom/realtime-stack.ts](amplify/custom/realtime-stack.ts)). This
  preserves the existing custom JSON wire protocol (`time_sync` / `live` / `backlog` /
  `position_update`) almost unchanged, so the mobile client needs little to no changes.
  Rejected: AppSync GraphQL subscriptions — would force a full protocol redesign (GraphQL
  mutations/subscriptions have no free-form `type`-keyed envelope) and a mobile client
  rewrite for no functional gain (no multi-subscriber fan-out need exists here).
- **Persistence: DynamoDB**, single table `DeviceTelemetry`, replacing Postgres/TimescaleDB
  and Redis entirely. `PK = "DEVICE#{device_id}"`; `SK = "STATE"` for the live EKF state
  item (replaces both Redis's `device:state:{device_id}` and the Postgres fallback in one
  GetItem/PutItem — see [lambdas/common/state_store.py](lambdas/common/state_store.py)),
  `SK = "TRAJ#{iso8601_ts}#{seq}"` for trajectory history rows (see
  [lambdas/common/trajectory_store.py](lambdas/common/trajectory_store.py)). Every existing
  query in [app/db/crud.py](app/db/crud.py) is single-table, no-join, partition+range —
  exactly DynamoDB's native pattern — and no TimescaleDB-specific feature (hypertable
  compression, `time_bucket()`, continuous aggregates) is used anywhere in the codebase, so
  keeping Postgres/RDS Proxy would add real operational cost for zero benefit. The unused
  `DeviceSession` table is dropped (no crud function touches it today).
- **Connections**: a separate `Connections` table
  ([lambdas/common/connections_store.py](lambdas/common/connections_store.py)) keyed by
  `connection_id`, with a `device_id-index` GSI (sorted by `connected_at` as its range key,
  so "most recent connection for this device" is well-defined) — replaces the module-level
  `active_connections: Dict[str, WebSocket]` in `app/api/websocket.py`, which cannot survive
  across Lambda invocations.
- **Auth: keep the existing self-issued JWT scheme** (HS256, `app/core/auth.py`) almost
  as-is — there is no real login today (`POST /auth/token` mints a token for any
  caller-supplied `device_id`, unauthenticated by design), so migrating to Cognito would
  invent an identity model nobody asked for. The one required fix: move `SECRET_KEY` out of
  the checked-in default in `app/config.py:13` into AWS Secrets Manager, fetched once per
  Lambda cold start. (Phase 4.)
- **Ordering/backlog**: `live` messages are processed synchronously inline in the `$default`
  Lambda (GetItem state → `kf.process_sample()` → PutItem state + trajectory row →
  `post_to_connection` reply) — no queue needed, structurally can't be blocked by anything.
  `backlog` chunks (from both the WS `backlog` message and the `POST /sensor-data` REST
  fallback) are published to an **SQS FIFO queue** with `MessageGroupId = device_id`
  (preserves today's per-device strict ordering without a shared process-wide queue), drained
  by a separate `backlog_consumer` Lambda that reuses the existing sort-by-`(seq, timestamp)`
  logic from [app/core/queue_manager.py](app/core/queue_manager.py). A DynamoDB conditional
  write (`require_newer_than` in `state_store.put_device_state()`) guards against the
  live-path and backlog-consumer racing on the same device's state item. (Phases 5-6.)
- **Critical bug fix required by this migration** (done in Phase 1, not optional):
  `IMUKalmanFilter.to_state_dict()`/`from_state_dict()` in
  [app/fusion/kalman_filter.py](app/fusion/kalman_filter.py) used to drop `_accel_history`
  (10-sample deque) and `_last_step_time` on every round-trip. That was a latent, minor
  accuracy gap under the old long-running process (the in-memory `device_kalman_filters`
  dict kept the live Python object, deque included, alive across packets). Under Lambda,
  **every single packet** is a cold deserialize from DynamoDB, so this bug would have
  permanently zeroed out the adaptive movement-state variance calculation and broken
  step-cadence detection entirely.

## File-level plan

```
Sih-Backend/
├── amplify/backend.ts, amplify/custom/realtime-stack.ts   # Gen 2 entry + CDK: WS API, SQS FIFO, DynamoDB, IAM
├── lambdas/
│   ├── ws_connect/, ws_disconnect/, ws_default/, backlog_consumer/   # done (Phase 3, stubs)
│   ├── rest_auth_token/, rest_sensor_data/, rest_health/, rest_trajectory/, rest_state/, rest_mode/   # not started
│   └── common/  # done (Phase 2): fusion/, time_sync.py, auth.py (not yet moved),
│                # state_store.py, trajectory_store.py, connections_store.py, dynamo.py
├── app/            # demoted: local-dev-only reference harness, not deployed
├── tests/unit/, tests/integration/, tests/smoke/verify_deployment.py  # unit/ started, rest not
```

**Reused nearly as-is** (move into `lambdas/common/`, no logic changes beyond the Phase 1
state-dict fix): [app/fusion/kalman_filter.py](app/fusion/kalman_filter.py),
[app/fusion/coordinates.py](app/fusion/coordinates.py),
[app/core/time_sync.py](app/core/time_sync.py), [app/core/auth.py](app/core/auth.py) (only
its settings source changes, to Secrets Manager — Phase 4).

**Rewritten**: [app/api/websocket.py](app/api/websocket.py) (module-level
`active_connections`/`device_kalman_filters` dicts and `restore_or_init_filter` become
`ws_connect`/`ws_disconnect`/`ws_default` + `state_store.py`/`connections_store.py`, the
latter two done in Phase 2); [app/core/queue_manager.py](app/core/queue_manager.py) (deleted
once Phase 6 lands, replaced by SQS FIFO, sort logic reused in `backlog_consumer`);
[app/api/rest_routes.py](app/api/rest_routes.py) (split into one Lambda per route — Phase 7,
see redefinitions below).

**Deleted** (once the corresponding phase lands): [app/cache/redis_client.py](app/cache/redis_client.py)
(its `InMemoryCacheFallback` is exactly the anti-pattern to avoid — per-invocation memory
that silently loses data between cold starts); [app/db/database.py](app/db/database.py),
[app/db/crud.py](app/db/crud.py), [app/db/models.py](app/db/models.py) (replaced by
`state_store.py`/`trajectory_store.py` over DynamoDB, done in Phase 2);
[app/main.py](app/main.py)'s uvicorn/lifespan/dashboard (no persistent process in Lambda).
`Dockerfile`, `docker-compose.yml`, `deploy.sh`, `render.yaml`, `Procfile`, `systemd/`,
`nginx.conf.example`, `run_windows.bat` become legacy/local-dev-only once Amplify is the
sole deployment target — not removed yet, since the old deploy paths still work today.

**Redefinitions to flag explicitly** (behavioral changes, not silent ports — Phase 7):
- `GET /health` — today reports in-process `len(active_connections)`/`queue_mgr.queue_size`;
  redefine as DynamoDB/SQS reachability + `ApproximateNumberOfMessages` (queue depth) +
  recent-heartbeat count from the connections table (eventually-consistent, not exact).
- `POST /device/{device_id}/mode` — today mutates the live in-memory filter object, silently
  no-ops if no active connection; redefined (Phase 2, `state_store.set_pending_mode()`/
  `consume_pending_mode()`) to write a `pending_mode` attribute onto the `STATE` item,
  applied and cleared on the next `live` packet once Phase 5 wires the live path to call
  `consume_pending_mode()` — always applied eventually, never a silent no-op.

**Tests to rewrite**: `tests/test_backend.py`'s `TestFastAPIRoutes` (no ASGI app anymore —
invoke Lambda handlers directly with `moto`-mocked AWS), `TestIngestionPriorityQueue`
(replaced by SQS FIFO ordering tests), `TestCacheManager` (deleted, its subject is gone);
Kalman/coordinates/auth/time_sync test classes carry over almost unchanged.
`tests/simulate_device.py` and `tests/verify_deployment.py` need rewriting for API Gateway
WebSocket + HTTP API URLs (Phase 8).

## Local development

- **Python (Lambda handlers + `lambdas/common/`)**: `pip install -r requirements-dev.txt`
  (pulls in `requirements.txt`, `lambdas/requirements.txt`, and `moto` for testing), then
  `python -m unittest discover -s tests -p "test_*.py"`.
- **Node/CDK (`amplify/`)**: `npm install`, then `npx tsc --noEmit -p amplify/tsconfig.json`
  (adjusted to include `backend.ts`/`custom/**/*.ts` — see the check performed for Phase 3)
  to type-check without deploying.
- **Deploying**: `npm run sandbox` (wraps `npx ampx sandbox`) — requires AWS credentials
  (`npx ampx configure profile` if none are set up yet). This has not been run successfully
  in this environment; it's the first remaining step for whoever has AWS account access.

## Verification

1. **Phase 1** ✅: fix `to_state_dict`/`from_state_dict` in `kalman_filter.py`, extend
   `test_kalman_filter_serialization`, run against the existing local Docker/uvicorn stack.
2. **Phase 2** ✅: `state_store.py`/`trajectory_store.py`/`connections_store.py` built and
   unit-tested against `moto`-mocked DynamoDB — 15 tests, all passing.
3. **Phase 3** — code done, deployment pending: scaffold `amplify/backend.ts` + custom CDK
   realtime stack; `cdk.App().synth()` confirmed valid without AWS credentials. **Remaining**:
   deploy via `npx ampx sandbox`, confirm the WebSocket API accepts connections with the stub
   integrations (e.g. via `wscat -c <WebSocketUrl-output>` and watching the stub echo reply).
4. **Phase 4**: auth Lambdas (`rest_auth_token`, `$connect` check, Secrets Manager for
   `SECRET_KEY`); verify JWT mint/verify round-trip against the sandbox.
5. **Phase 5**: `ws_default` live fast-path; smoke-test connect → `time_sync` →
   `time_sync_ack` → `live` frames → `position_update` replies against the sandbox.
6. **Phase 6**: SQS FIFO + `backlog_consumer` + `/sensor-data`; smoke-test the backlog path
   (disconnect, accumulate, reconnect, send backlog, poll `/device/{id}/state` until it
   reflects the final position — now asynchronous, unlike today).
7. **Phase 7**: remaining REST reads, redefined `/health` and `/device/{id}/mode`; full
   smoke suite (rewritten `verify_deployment.py`) passing end-to-end against the sandbox.
8. **Phase 8**: validate the real mobile client against the sandbox WS URL, run the rewritten
   smoke tests against a promoted Amplify branch, then decommission the Docker/EC2/Render/
   systemd deployment paths only after a burn-in period — don't delete them same-day as cutover.
