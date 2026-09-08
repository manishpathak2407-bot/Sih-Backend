import logging
from collections import deque, defaultdict
from typing import Dict, Any, Optional, Tuple
import numpy as np
from app.config import get_settings
from app.cache.redis_client import cache_manager
from app.cache.window_hasher import compute_window_hash
from app.ml.model_interface import BaseDriftCorrectionModel

logger = logging.getLogger(__name__)
settings = get_settings()

class MLBridge:
    """
    Backend Integration Gateway for the MLA Team's Model.
    
    Responsibilities:
    - Buffers the rolling 10Hz sensor window (10 samples = 1 second).
    - Prevents redundant AI computation by hashing the window and caching results in Redis.
    - Provides a plug-and-play hook (register_model) for the MLA team.
    - If no model is registered, defaults to zero drift (pure statistical Kalman fusion).
    """
    def __init__(self):
        self.model: Optional[BaseDriftCorrectionModel] = None
        self.window_size = settings.WINDOW_SIZE  # 10 samples at 10Hz
        self._device_windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.window_size))
        self.cache_hits = 0
        self.cache_misses = 0

    def register_model(self, model: BaseDriftCorrectionModel):
        """Hook for the MLA team to attach their model at startup or runtime."""
        self.model = model
        logger.info(f"[ML Bridge] Successfully registered MLA model: {model.model_name}")

    def add_sample(self, device_id: str, packet: Dict[str, Any]):
        """Append a 10Hz sample to the device's temporal window."""
        sample = [
            packet.get("ax", 0.0),
            packet.get("ay", 0.0),
            packet.get("az", 0.0),
            packet.get("gx", 0.0),
            packet.get("gy", 0.0),
            packet.get("gz", 0.0),
            packet.get("mx", 0.0),
            packet.get("my", 0.0),
            packet.get("mz", 0.0),
        ]
        self._device_windows[device_id].append(sample)

    async def get_drift_correction(self, device_id: str) -> Tuple[np.ndarray, bool]:
        """
        Returns (drift_vector, is_cache_hit).
        If the external MLA model is not yet registered or window not full, returns zero drift.
        """
        if self.model is None:
            return np.zeros(3, dtype=np.float32), False

        window = self._device_windows[device_id]
        if len(window) < self.window_size:
            return np.zeros(3, dtype=np.float32), False

        window_arr = np.array(window, dtype=np.float32)
        cache_key = compute_window_hash(device_id, window_arr)

        # 1. Check Redis Cache Layer (O(1) duplicate/backlog check)
        cached_drift = await cache_manager.get_ml_correction(cache_key)
        if cached_drift is not None:
            self.cache_hits += 1
            return np.array(cached_drift["drift"], dtype=np.float32), True

        # 2. Cache Miss: Execute Registered MLA Model
        self.cache_misses += 1
        drift = self.model.predict_drift(window_arr)

        # 3. Cache Result in Redis (TTL = 30 minutes)
        await cache_manager.set_ml_correction(
            cache_key,
            {"drift": drift.tolist() if hasattr(drift, "tolist") else list(drift), "model": self.model.model_name}
        )
        return np.array(drift, dtype=np.float32), False

    def get_metrics(self) -> Dict[str, Any]:
        total = self.cache_hits + self.cache_misses
        hit_ratio = (self.cache_hits / total) if total > 0 else 0.0
        return {
            "is_model_registered": self.model is not None,
            "model_name": self.model.model_name if self.model else "None (Pure Kalman Mode)",
            "window_size_samples": self.window_size,
            "sampling_rate_hz": settings.IMU_SAMPLING_RATE_HZ,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_ratio_percent": round(hit_ratio * 100, 2)
        }

ml_bridge = MLBridge()
