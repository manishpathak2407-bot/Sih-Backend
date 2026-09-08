import logging
from collections import deque, defaultdict
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from app.config import get_settings
from app.cache.redis_client import cache_manager
from app.cache.window_hasher import compute_window_hash
from app.ml.model_interface import BaseDriftCorrectionModel
from app.ml.default_model import DefaultNeuralDriftModel

logger = logging.getLogger(__name__)
settings = get_settings()

class MLBridge:
    """
    Coordinates between the streaming IMU windows, the Redis Window-Hash Cache,
    and the Deep Learning Drift Model.
    
    Prevents redundant AI computation by caching ML outputs by input window content hash.
    """
    def __init__(self, model: Optional[BaseDriftCorrectionModel] = None):
        self.model: BaseDriftCorrectionModel = model if model else DefaultNeuralDriftModel()
        self.window_size = settings.WINDOW_SIZE
        # Per-device rolling sensor buffer
        self._device_windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.window_size))
        # Metrics
        self.cache_hits = 0
        self.cache_misses = 0

    def add_sample(self, device_id: str, packet: Dict[str, Any]):
        """Append sample to device's sliding window."""
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
        If the window hasn't filled yet, returns zero drift.
        """
        window = self._device_windows[device_id]
        if len(window) < min(10, self.window_size):
            return np.zeros(3, dtype=np.float32), False

        window_arr = np.array(window, dtype=np.float32)
        cache_key = compute_window_hash(device_id, window_arr)

        # 1. Check Redis Cache
        cached_drift = await cache_manager.get_ml_correction(cache_key)
        if cached_drift is not None:
            self.cache_hits += 1
            logger.debug(f"[CACHE HIT] O(1) retrieved drift for {device_id}")
            return np.array(cached_drift["drift"], dtype=np.float32), True

        # 2. Cache Miss: Execute Model Forward Pass
        self.cache_misses += 1
        drift = self.model.predict_drift(window_arr)

        # 3. Cache Result in Redis (TTL = 30 minutes)
        await cache_manager.set_ml_correction(
            cache_key,
            {"drift": drift.tolist(), "model": self.model.model_name}
        )
        return drift, False

    def get_metrics(self) -> Dict[str, Any]:
        total = self.cache_hits + self.cache_misses
        hit_ratio = (self.cache_hits / total) if total > 0 else 0.0
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_ratio_percent": round(hit_ratio * 100, 2),
            "model_name": self.model.model_name
        }

ml_bridge = MLBridge()
