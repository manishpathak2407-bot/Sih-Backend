import logging
import os
import numpy as np
from typing import Optional
from app.ml.model_interface import BaseDriftCorrectionModel

logger = logging.getLogger(__name__)

class DefaultNeuralDriftModel(BaseDriftCorrectionModel):
    """
    Default plug-and-play Drift Correction Model.
    
    Acts as the bridge for your teammate's trained model.
    Can run pure NumPy heuristic drift estimation or load PyTorch (.pt) / ONNX (.onnx) models.
    """
    def __init__(self, model_path: Optional[str] = None):
        self._model_name = "Intelligent-IMU-DriftCorrector-v1"
        self._weights_loaded = False
        self._torch_model = None
        self._onnx_session = None

        if model_path and os.path.exists(model_path):
            self.load_weights(model_path)

    @property
    def model_name(self) -> str:
        return self._model_name

    def load_weights(self, weights_path: str) -> bool:
        """
        Loads PyTorch (.pt) or ONNX (.onnx) weights provided by your ML teammate.
        """
        try:
            if weights_path.endswith(".pt") or weights_path.endswith(".pth"):
                import torch
                self._torch_model = torch.jit.load(weights_path) if weights_path.endswith(".pt") else torch.load(weights_path)
                self._torch_model.eval()
                self._weights_loaded = True
                logger.info(f"Loaded PyTorch model from {weights_path}")
                return True
            elif weights_path.endswith(".onnx"):
                import onnxruntime as ort
                self._onnx_session = ort.InferenceSession(weights_path)
                self._weights_loaded = True
                logger.info(f"Loaded ONNX model from {weights_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to load weights from {weights_path}: {e}")
            return False
        return False

    def predict_drift(self, sensor_window: np.ndarray) -> np.ndarray:
        """
        Runs neural inference to predict non-linear IMU bias drift over the current window.
        Returns: [drift_x, drift_y, drift_z] in meters.
        """
        if self._weights_loaded and self._torch_model is not None:
            import torch
            with torch.no_grad():
                tensor_in = torch.from_numpy(sensor_window).float().unsqueeze(0)
                out = self._torch_model(tensor_in).squeeze(0).numpy()
                return out[:3]

        if self._weights_loaded and self._onnx_session is not None:
            input_name = self._onnx_session.get_inputs()[0].name
            out = self._onnx_session.run(None, {input_name: sensor_window.astype(np.float32)[np.newaxis, ...]})[0]
            return out[0][:3]

        # Default kinematic drift estimator when custom weights aren't mounted yet:
        # Analyzes mean gyro bias and low-frequency acceleration drift
        gyro_drift = np.mean(sensor_window[:, 3:6], axis=0) * 0.05
        accel_mean = np.mean(sensor_window[:, 0:3], axis=0)
        
        # Estimate pedestrian step drift
        drift_x = float(gyro_drift[2] * 0.02 + (accel_mean[0] * 0.01))
        drift_y = float(gyro_drift[1] * 0.02 + (accel_mean[1] * 0.01))
        drift_z = float(gyro_drift[0] * 0.01)

        return np.array([drift_x, drift_y, drift_z], dtype=np.float32)
