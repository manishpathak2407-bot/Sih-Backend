from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import numpy as np

class BaseDriftCorrectionModel(ABC):
    """
    Standard interface for your team's ML Dead Reckoning drift correction model.
    Any deep learning model (BiLSTM, GRU, TCN, ResNet-1D, etc.) must implement this interface.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable name of the ML architecture."""
        pass

    @abstractmethod
    def predict_drift(self, sensor_window: np.ndarray) -> np.ndarray:
        """
        Input:
            sensor_window: np.ndarray of shape (window_size, channels), e.g. (50, 6) or (50, 9)
            Channels typically: [ax, ay, az, gx, gy, gz, (mx, my, mz)]
            
        Output:
            drift_vector: np.ndarray of shape (3,) representing [dx, dy, dz] drift offsets
            or velocity correction vector in meters / m/s.
        """
        pass

    @abstractmethod
    def load_weights(self, weights_path: str) -> bool:
        """Load trained weights (.pt, .onnx, .h5, etc.)."""
        pass
