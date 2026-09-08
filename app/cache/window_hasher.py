import hashlib
import numpy as np
from typing import Union, List

def compute_window_hash(device_id: str, sensor_window: Union[np.ndarray, List[List[float]]], decimals: int = 3) -> str:
    """
    Computes a deterministic hash for a temporal window of IMU sensor readings.
    
    Quantizes sensor floats to `decimals` places to filter out high-frequency noise
    while preserving meaningful motion kinematics.
    
    Returns a cache key string: ml_cache:{device_id}:{sha256_hash_16_chars}
    """
    if not isinstance(sensor_window, np.ndarray):
        arr = np.array(sensor_window, dtype=np.float32)
    else:
        arr = sensor_window.astype(np.float32)

    # Quantize to eliminate sub-noise float jitter
    quantized = np.round(arr, decimals=decimals)
    
    # Deterministic byte representation
    raw_bytes = quantized.tobytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
    
    return f"ml_cache:{device_id}:{digest}"
