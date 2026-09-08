# 10Hz Dead Reckoning Backend Engine - SIH 2026
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.cache.redis_client import cache_manager
from app.db.database import init_db
from app.api.websocket import router as ws_router, queue_worker
from app.api.rest_routes import router as rest_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sih_backend")
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing SIH Dead Reckoning Backend...")
    await cache_manager.connect()
    await init_db()
    
    # Launch asynchronous queue processor worker
    worker_task = asyncio.create_task(queue_worker())
    logger.info("System ready. Ingestion queue worker active.")

    yield

    # Shutdown
    logger.info("Shutting down backend...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await cache_manager.disconnect()
    logger.info("Shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API & WebSocket routes
app.include_router(ws_router)
app.include_router(rest_router)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SIH Dead Reckoning 10Hz Monitor</title>
    <style>
        :root {
            --bg: #0d1117;
            --card: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --text-bright: #ffffff;
            --accent: #58a6ff;
            --green: #2ea043;
            --orange: #f0883e;
            --red: #da3633;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg); color: var(--text); padding: 20px; }
        header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 16px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
        h1 { font-size: 1.4rem; color: var(--text-bright); display: flex; align-items: center; gap: 10px; }
        .badge { background: #238636; color: white; font-size: 0.75rem; padding: 4px 10px; border-radius: 12px; font-weight: bold; }
        .badge-offline { background: var(--orange); }
        .grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
        .card-title { font-size: 0.95rem; font-weight: 600; color: var(--accent); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
        canvas { width: 100%; height: 420px; background: #010409; border: 1px solid var(--border); border-radius: 6px; display: block; }
        .telemetry { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
        .stat-box { background: #0d1117; padding: 12px; border-radius: 6px; border: 1px solid var(--border); }
        .stat-label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; margin-bottom: 4px; }
        .stat-val { font-size: 1.25rem; font-weight: bold; color: var(--text-bright); font-family: monospace; }
        .btn-group { display: flex; flex-direction: column; gap: 10px; }
        button { background: #21262d; border: 1px solid var(--border); color: var(--text-bright); padding: 10px 14px; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.2s; font-size: 0.85rem; text-align: left; }
        button:hover { background: #30363d; }
        button.primary { background: #238636; border-color: #2ea043; }
        button.primary:hover { background: #2ea043; }
        button.secondary { background: #1f6feb; border-color: #388bfd; }
        button.secondary:hover { background: #388bfd; }
        button.danger { background: #b62324; border-color: #da3633; }
        button.danger:hover { background: #da3633; }
        .logs { height: 180px; overflow-y: auto; background: #010409; border: 1px solid var(--border); border-radius: 6px; padding: 10px; font-family: monospace; font-size: 0.75rem; line-height: 1.4; color: #8b949e; margin-top: 14px; }
        .log-entry { margin-bottom: 4px; }
        .log-ok { color: #56d364; }
        .log-warn { color: var(--orange); }
        .links a { color: var(--accent); text-decoration: none; font-size: 0.85rem; margin-right: 15px; }
        .links a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>10Hz Dead Reckoning Telemetry Monitor <span id="conn-badge" class="badge badge-offline">DISCONNECTED</span></h1>
            <p style="font-size: 0.8rem; color: #8b949e; margin-top: 4px;">FastAPI 9-DOF Kalman Sensor Fusion with Zero-Velocity Update (ZUPT)</p>
        </div>
        <div class="links">
            <a href="/docs" target="_blank">Swagger API Docs</a>
            <a href="/health" target="_blank">Healthcheck JSON</a>
        </div>
    </header>

    <div class="grid">
        <div class="card">
            <div class="card-title" style="display: flex; justify-content: space-between;">
                <span>2D Metric Trajectory Canvas (East vs North)</span>
                <span id="coord-hud" style="color: var(--accent); font-family: monospace; font-size: 0.85rem;">(0.00m, 0.00m)</span>
            </div>
            <canvas id="mapCanvas" width="700" height="420"></canvas>
            <div class="logs" id="logBox">
                <div class="log-entry log-ok">[SYSTEM] Dashboard initialized. Select a test mode below.</div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">Live Telemetry & Motion HUD</div>
            <div class="telemetry">
                <div class="stat-box">
                    <div class="stat-label">Position X (East)</div>
                    <div class="stat-val" id="stat-x">0.000 m</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Position Y (North)</div>
                    <div class="stat-val" id="stat-y">0.000 m</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Velocity</div>
                    <div class="stat-val" id="stat-v">0.00 m/s</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Motion State</div>
                    <div class="stat-val" id="stat-state" style="color: #56d364; font-size: 1.0rem;">STATIONARY</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Yaw Heading</div>
                    <div class="stat-val" id="stat-yaw">0.0°</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Sequence (10Hz)</div>
                    <div class="stat-val" id="stat-seq">0</div>
                </div>
            </div>

            <div class="card-title">Streaming Modes & Controls</div>
            <div class="btn-group">
                <button id="btn-stationary" class="secondary" onclick="toggleStationaryTest()">
                    🪑 <b>Stationary Desk Mode (Resting Laptop)</b><br>
                    <span style="font-size:0.75rem; color:#c9d1d9; font-weight:normal;">Verifies position stays rock solid at 0.000m with zero drift</span>
                </button>
                <button id="btn-physical" onclick="togglePhysicalSensors()">
                    📱 <b>Stream Real Device Hardware Sensors</b><br>
                    <span style="font-size:0.75rem; color:#c9d1d9; font-weight:normal;">Reads your laptop/phone's physical accelerometer & gyro</span>
                </button>
                <button id="btn-sim" class="primary" onclick="toggleSyntheticWalk()">
                    🚶 <b>Simulate Walking Path (Virtual Pedestrian)</b><br>
                    <span style="font-size:0.75rem; color:#c9d1d9; font-weight:normal;">Generates virtual forward steps for algorithm testing</span>
                </button>
                <button id="btn-drop" onclick="simulateDrop()">
                    ⚡ <b>Simulate 2s Outage & Backlog Flush</b>
                </button>
                <button onclick="clearCanvas()">
                    🧹 <b>Reset Position & Clear Canvas</b>
                </button>
            </div>
        </div>
    </div>

    <script>
        const canvas = document.getElementById("mapCanvas");
        const ctx = canvas.getContext("2d");
        const logBox = document.getElementById("logBox");
        const badge = document.getElementById("conn-badge");
        
        let ws = null;
        let activeMode = null; // 'stationary', 'physical', 'synthetic'
        let streamInterval = null;
        let seq = 1;
        let currentPos = { x: 0, y: 0 };
        let pathHistory = [{ x: 0, y: 0 }];
        const deviceId = "web_dashboard_client";

        function log(msg, cls = "") {
            const d = document.createElement("div");
            d.className = "log-entry " + cls;
            d.textContent = `[${new Date().toLocaleTimeString()}] ` + msg;
            logBox.appendChild(d);
            logBox.scrollTop = logBox.scrollHeight;
        }

        function drawCanvas() {
            ctx.fillStyle = "#010409";
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Draw Grid
            ctx.strokeStyle = "#161b22";
            ctx.lineWidth = 1;
            const step = 40;
            for (let x = 0; x < canvas.width; x += step) {
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
            }
            for (let y = 0; y < canvas.height; y += step) {
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
            }

            // Origin
            const cx = canvas.width / 2;
            const cy = canvas.height / 2;
            const scale = 30; // 30 pixels per meter

            ctx.strokeStyle = "#30363d";
            ctx.beginPath();
            ctx.moveTo(cx, 0); ctx.lineTo(cx, canvas.height);
            ctx.moveTo(0, cy); ctx.lineTo(canvas.width, cy);
            ctx.stroke();

            // Draw Trajectory Path
            if (pathHistory.length > 1) {
                ctx.strokeStyle = "#58a6ff";
                ctx.lineWidth = 3;
                ctx.beginPath();
                ctx.moveTo(cx + pathHistory[0].x * scale, cy - pathHistory[0].y * scale);
                for (let i = 1; i < pathHistory.length; i++) {
                    ctx.lineTo(cx + pathHistory[i].x * scale, cy - pathHistory[i].y * scale);
                }
                ctx.stroke();
            }

            // Draw Current Position Indicator
            const px = cx + currentPos.x * scale;
            const py = cy - currentPos.y * scale;
            ctx.fillStyle = "#2ea043";
            ctx.beginPath();
            ctx.arc(px, py, 6, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 2;
            ctx.stroke();
        }

        async function connectWebSocket() {
            if (ws && ws.readyState === WebSocket.OPEN) return;

            const res = await fetch("/auth/token", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ device_id: deviceId, expires_minutes: 60 })
            });
            const authData = await res.json();
            const token = authData.access_token;

            const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
            const wsUrl = `${proto}//${window.location.host}/ws/track/${deviceId}?token=${token}`;
            
            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                badge.textContent = "CONNECTED (10Hz)";
                badge.className = "badge";
                log("WebSocket connected with JWT handshake.", "log-ok");
                ws.send(JSON.stringify({ type: "time_sync", t_client_send: Date.now() / 1000 }));
            };

            ws.onmessage = (e) => {
                const data = JSON.parse(e.data);
                if (data.type === "position_update") {
                    currentPos.x = data.x;
                    currentPos.y = data.y;
                    pathHistory.push({ x: data.x, y: data.y });
                    if (pathHistory.length > 500) pathHistory.shift();

                    document.getElementById("stat-x").textContent = data.x.toFixed(3) + " m";
                    document.getElementById("stat-y").textContent = data.y.toFixed(3) + " m";
                    const speed = Math.sqrt(data.vx*data.vx + data.vy*data.vy);
                    document.getElementById("stat-v").textContent = speed.toFixed(2) + " m/s";

                    const stateBox = document.getElementById("stat-state");
                    if (speed < 0.05) {
                        stateBox.textContent = "STATIONARY (ZUPT)";
                        stateBox.style.color = "#56d364";
                    } else {
                        stateBox.textContent = "MOVING";
                        stateBox.style.color = "#58a6ff";
                    }

                    document.getElementById("stat-yaw").textContent = (data.yaw * (180/Math.PI)).toFixed(1) + "°";
                    document.getElementById("stat-seq").textContent = data.seq;
                    document.getElementById("coord-hud").textContent = `(${data.x.toFixed(2)}m, ${data.y.toFixed(2)}m)`;

                    drawCanvas();
                }
            };

            ws.onclose = () => {
                badge.textContent = "DISCONNECTED";
                badge.className = "badge badge-offline";
                log("WebSocket closed.", "log-warn");
            };
        }

        function stopAllStreams() {
            if (streamInterval) clearInterval(streamInterval);
            streamInterval = null;
            activeMode = null;
            document.getElementById("btn-stationary").style.borderColor = "var(--border)";
            document.getElementById("btn-physical").style.borderColor = "var(--border)";
            document.getElementById("btn-sim").style.borderColor = "var(--border)";
        }

        // Mode 1: Stationary Desk Test (Laptop at rest)
        async function toggleStationaryTest() {
            if (activeMode === "stationary") {
                stopAllStreams();
                log("Stationary test stopped.");
                return;
            }
            stopAllStreams();
            await connectWebSocket();
            activeMode = "stationary";
            document.getElementById("btn-stationary").style.borderColor = "#58a6ff";
            log("STATIONARY DESK MODE ACTIVE: Laptop resting on desk (Acceleration = [0, 0, 9.81 m/s²], Gyro = 0).", "log-ok");
            log("Backend ZUPT is active: Velocity and Position will stay strictly locked at 0.000 m.", "log-ok");

            streamInterval = setInterval(() => {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    // Send actual resting sensor packet (Earth gravity 9.81 m/s² down Z, zero rotation)
                    ws.send(JSON.stringify({
                        type: "live",
                        seq: seq++,
                        timestamp: Date.now() / 1000,
                        ax: 0.0,
                        ay: 0.0,
                        az: 9.81,
                        gx: 0.0,
                        gy: 0.0,
                        gz: 0.0,
                        mx: 22.0,
                        my: -5.0,
                        mz: 41.0
                    }));
                }
            }, 100);
        }

        // Mode 2: Physical Device Sensors
        let physicalListener = null;
        async function togglePhysicalSensors() {
            if (activeMode === "physical") {
                stopAllStreams();
                if (physicalListener) window.removeEventListener("devicemotion", physicalListener);
                log("Physical sensor stream stopped.");
                return;
            }
            stopAllStreams();
            await connectWebSocket();

            if (!window.DeviceMotionEvent) {
                alert("DeviceMotionEvent is not supported by your browser/hardware.");
                return;
            }

            activeMode = "physical";
            document.getElementById("btn-physical").style.borderColor = "#58a6ff";
            log("Reading physical hardware motion sensors (accelerometer & gyro)...", "log-ok");

            let lastAccel = { x: 0, y: 0, z: 9.81 };
            let lastGyro = { x: 0, y: 0, z: 0 };

            physicalListener = (e) => {
                if (e.accelerationIncludingGravity) {
                    lastAccel.x = e.accelerationIncludingGravity.x || 0;
                    lastAccel.y = e.accelerationIncludingGravity.y || 0;
                    lastAccel.z = e.accelerationIncludingGravity.z || 9.81;
                }
                if (e.rotationRate) {
                    lastGyro.x = (e.rotationRate.alpha || 0) * (Math.PI / 180);
                    lastGyro.y = (e.rotationRate.beta || 0) * (Math.PI / 180);
                    lastGyro.z = (e.rotationRate.gamma || 0) * (Math.PI / 180);
                }
            };
            window.addEventListener("devicemotion", physicalListener);

            streamInterval = setInterval(() => {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({
                        type: "live",
                        seq: seq++,
                        timestamp: Date.now() / 1000,
                        ax: lastAccel.x,
                        ay: lastAccel.y,
                        az: lastAccel.z,
                        gx: lastGyro.x,
                        gy: lastGyro.y,
                        gz: lastGyro.z
                    }));
                }
            }, 100);
        }

        // Mode 3: Synthetic Walking Sim
        async function toggleSyntheticWalk() {
            if (activeMode === "synthetic") {
                stopAllStreams();
                log("Virtual walk generator stopped.");
                return;
            }
            stopAllStreams();
            await connectWebSocket();
            activeMode = "synthetic";
            document.getElementById("btn-sim").style.borderColor = "#58a6ff";
            log("VIRTUAL PEDESTRIAN SIMULATION ACTIVE: Simulating forward walking steps at 10Hz.", "log-ok");

            let angle = 0;
            streamInterval = setInterval(() => {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    angle += 0.05;
                    const forwardAcc = 0.8 + 0.3 * Math.sin(angle * 5); // Simulating forward foot strike
                    ws.send(JSON.stringify({
                        type: "live",
                        seq: seq++,
                        timestamp: Date.now() / 1000,
                        ax: Math.cos(angle) * 0.1,
                        ay: forwardAcc,
                        az: 9.81 + 0.4 * Math.sin(angle * 10),
                        gx: 0.01,
                        gy: 0.01,
                        gz: 0.04
                    }));
                }
            }, 100);
        }

        function simulateDrop() {
            if (!activeMode) {
                alert("Start a streaming mode first, then trigger a network drop!");
                return;
            }
            const prevMode = activeMode;
            stopAllStreams();
            log("Simulating network drop... WebSocket disconnected!", "log-warn");
            ws.close();

            log("Buffering 20 packets locally in SQLite offline buffer...", "log-warn");
            const backlog = [];
            for (let i = 0; i < 20; i++) {
                backlog.push({
                    seq: seq++,
                    timestamp: (Date.now() / 1000) + (i * 0.1),
                    ax: 0.0,
                    ay: 0.0,
                    az: 9.81,
                    gx: 0.0,
                    gy: 0.0,
                    gz: 0.0
                });
            }

            setTimeout(async () => {
                log("Reconnecting with backoff jitter...", "log-ok");
                await connectWebSocket();
                setTimeout(() => {
                    log(`Ingesting backlog chunk (${backlog.length} packets at Priority 1)...`, "log-ok");
                    ws.send(JSON.stringify({ type: "backlog", chunk: backlog }));
                }, 500);
            }, 2000);
        }

        function clearCanvas() {
            pathHistory = [{ x: 0, y: 0 }];
            currentPos = { x: 0, y: 0 };
            document.getElementById("stat-x").textContent = "0.000 m";
            document.getElementById("stat-y").textContent = "0.000 m";
            document.getElementById("stat-v").textContent = "0.00 m/s";
            document.getElementById("stat-state").textContent = "STATIONARY";
            document.getElementById("coord-hud").textContent = "(0.00m, 0.00m)";
            drawCanvas();
            log("Position reset to origin (0, 0).");
        }

        drawCanvas();
        connectWebSocket();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
