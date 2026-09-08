# AI-ML Dead Reckoning Backend Engine (10Hz)
**High-Concurrency FastAPI Ingestion, Priority Queues, Redis Caching & TimescaleDB Persistence**

---

## 1. Overview & Scope

This repository contains the **pure backend service** for the Smart India Hackathon (SIH) Dead Reckoning navigation system. It does not contain frontend or machine learning training code; instead, it provides production-grade backend infrastructure designed to integrate with:
1. **The App Dev Team:** Streams 10Hz IMU packets over authenticated WebSockets, syncs clock drift, and receives real-time ML-corrected positions.
2. **The MLA (Machine Learning Algorithm) Team:** Plugs directly into the backend via a standardized interface ([`app/ml/model_interface.py`](file:///C:/Users/manis/OneDrive/Desktop/Sih-Backend/app/ml/model_interface.py)) without touching networking, databases, or queue logic.

---

## 2. Technical Specifications (10Hz Standard)

- **Sampling Frequency:** **10 Hz** (100ms packet interval, $\Delta t = 0.1\text{s}$).
- **Temporal Window Size:** 10 samples (1-second sliding window).
- **Transport Protocols:** Full-duplex WebSocket (`/ws/track/{device_id}`) with REST fallback (`/sensor-data`).
- **Security:** HMAC-SHA256 JWT handshake authentication.
- **Clock Drift Compensation:** 3-way NTP handshake calculating $\Delta t_{\text{offset}}$ and RTT.
- **Starvation-Free Queue:** `asyncio.PriorityQueue` prioritizing Live 10Hz frames (`P0`) over Backlog recovery dumps (`P1`).
- **Caching Layer:** Redis 7+ with content-hashing (SHA-256) on quantized 10Hz windows to eliminate redundant ML forward passes.
- **Persistence:** PostgreSQL 16 + TimescaleDB hypertables for long-term trajectory storage.

---

## 3. Integration Contracts

### A. For the App Dev Team (Frontend / Mobile Client)

#### 1. WebSocket Endpoint
```text
ws://<server_host>:8000/ws/track/{device_id}?token=<jwt_token>
```
*Token can be obtained via `POST /auth/token` with body `{"device_id": "...", "expires_minutes": 60}`.*

#### 2. Handshake & NTP Clock Sync
Immediately after connecting, the client sends:
```json
{
  "type": "time_sync",
  "t_client_send": 1725780000.123
}
```
The backend immediately replies with `t_server_recv` and `t_server_send` to compute client clock skew.

#### 3. Real-Time Live Streaming (10Hz, Priority 0)
Send continuous 100ms interval frames:
```json
{
  "type": "live",
  "seq": 1,
  "timestamp": 1725780000.223,
  "ax": 0.05, "ay": 0.98, "az": 9.81,
  "gx": 0.01, "gy": 0.02, "gz": -0.01,
  "mx": 22.5, "my": -5.1, "mz": 41.2
}
```

#### 4. Offline Backlog Ingestion (Priority 1)
When reconnecting after an outage, send buffered data in manageable chunks (max 20–50 packets per chunk):
```json
{
  "type": "backlog",
  "chunk": [
    {"seq": 25, "timestamp": 1725780002.500, "ax": 0.04, "ay": 0.95, "az": 9.80, "gx": 0.0, "gy": 0.0, "gz": 0.0, "mx": 22.0, "my": -5.0, "mz": 41.0},
    {"seq": 26, "timestamp": 1725780002.600, "ax": 0.06, "ay": 0.96, "az": 9.82, "gx": 0.0, "gy": 0.0, "gz": 0.0, "mx": 22.1, "my": -5.1, "mz": 41.1}
  ]
}
```

#### 5. Position Feedback Stream (Server $\to$ Client)
The backend pushes back verified coordinates:
```json
{
  "type": "position_update",
  "device_id": "phone_user_sih_01",
  "seq": 26,
  "timestamp": 1725780002.600,
  "x": 4.521,
  "y": 12.834,
  "z": 0.120,
  "vx": 1.25, "vy": 0.11, "vz": 0.01,
  "yaw": 0.354,
  "is_backlog": false,
  "is_cache_hit": false,
  "is_verified": true
}
```

---

### B. For the MLA (Machine Learning Algorithm) Team

The MLA team implements the model in [`app/ml/model_interface.py`](file:///C:/Users/manis/OneDrive/Desktop/Sih-Backend/app/ml/model_interface.py):

```python
from app.ml.model_interface import BaseDriftCorrectionModel
import numpy as np

class MLAModel(BaseDriftCorrectionModel):
    @property
    def model_name(self) -> str:
        return "Trained-LSTM-DriftModel-v1"

    def predict_drift(self, sensor_window: np.ndarray) -> np.ndarray:
        """
        Args:
            sensor_window: np.ndarray of shape (10, 9) at 10Hz (1-second temporal window).
                           Columns: [ax, ay, az, gx, gy, gz, mx, my, mz]
        Returns:
            drift: np.ndarray of shape (3,) -> [dx, dy, dz] in meters
        """
        # Execute your model forward pass here
        return np.array([0.0, 0.0, 0.0], dtype=np.float32)
```

To register the model into the backend pipeline:
```python
from app.ml.ml_bridge import ml_bridge
from app.ml.my_mla_model import MLAModel

ml_bridge.register_model(MLAModel())
```
*The backend automatically manages window slicing, input-window SHA-256 deduplication, and Redis caching for the model.*

---

## 4. Key Architectural Mechanisms

1. **Starvation-Free Backlog Ingestion:** Live 10Hz packets enter the priority queue at `Priority 0`, while backlog chunks enter at `Priority 1` and cooperatively yield to the event loop (`await asyncio.sleep(0)`). Live streams maintain $<50\text{ms}$ latency even during large backlog floods.
2. **Window-Hash Deduplication:** Backlogs with overlapping sliding windows are hashed into Redis with a 30-minute TTL. Subsequent overlapping queries hit Redis in $\mathcal{O}(1)$ time, skipping redundant ML computation.
3. **Multi-Tier State Recovery:** If a device stays offline longer than the 1-hour Redis TTL, the backend queries TimescaleDB/PostgreSQL for the last known position and covariance matrix to restore the 9-DOF Kalman filter.

---

## 5. Running the Backend

### Local Python Run:
```powershell
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
*(Automatically falls back to SQLite and in-memory LRU cache if Redis/Postgres are not installed).*

### Docker Production Stack:
```powershell
docker compose up -d
```

### Integration Test:
```powershell
python tests/simulate_device.py
```
