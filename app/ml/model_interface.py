from abc import ABC, abstractmethod
import numpy as np

class BaseDriftCorrectionModel(ABC):
    """
    Integration Interface for External MLA (Machine Learning Algorithm) Team.
    
    The backend exposes this interface so the MLA team can plug in their model
    without modifying any backend, WebSocket, database, or queue logic.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name/Identifier of the ML model."""
        pass

    @abstractmethod
    def predict_drift(self, sensor_window: np.ndarray) -> np.ndarray:
        """
        Input:
            sensor_window: np.ndarray of shape (10, 9) at 10Hz (1-second window)
                           Columns: [ax, ay, az, gx, gy, gz, mx, my, mz]
        Output:
            drift_vector: np.ndarray of shape (3,) representing [dx, dy, dz] in meters
        """
        pass
