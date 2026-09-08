import numpy as np
from typing import Dict, Any, Optional
from app.fusion.coordinates import (
    body_to_nav_acceleration,
    calculate_tilt_compensated_heading,
    GRAVITY
)

class IMUKalmanFilter:
    """
    9-DOF Extended Kalman Filter for Dead Reckoning tuned for 10 Hz IMU streams.
    Fuses Accelerometer (3-axis), Gyroscope (3-axis), and Magnetometer (3-axis).
    
    State Vector (9 elements):
    x = [px, py, pz, vx, vy, vz, roll, pitch, yaw]^T
    """
    def __init__(self, initial_state: Optional[np.ndarray] = None, initial_covariance: Optional[np.ndarray] = None):
        # 9x1 State Vector
        if initial_state is not None:
            self.x = initial_state.astype(np.float64)
        else:
            self.x = np.zeros((9, 1), dtype=np.float64)

        # 9x9 Error Covariance Matrix
        if initial_covariance is not None:
            self.P = initial_covariance.astype(np.float64)
        else:
            self.P = np.eye(9, dtype=np.float64) * 0.1

        # Process Noise Covariance (Q) - Tuned for 10Hz (dt = 0.1s)
        self.Q = np.eye(9, dtype=np.float64) * 0.05
        self.Q[0:3, 0:3] *= 0.02  # Position uncertainty
        self.Q[3:6, 3:6] *= 0.15  # Velocity process noise
        self.Q[6:9, 6:9] *= 0.05  # Angular process noise

        # Measurement Noise Covariance (R)
        self.R = np.eye(3, dtype=np.float64) * 0.2

        self.last_timestamp: Optional[float] = None

    def predict(self, accel_body: np.ndarray, gyro_body: np.ndarray, dt: float):
        """
        Kinematic prediction step over elapsed time dt (seconds).
        For 10Hz streams, dt is typically ~0.10s.
        """
        if dt <= 0.0:
            dt = 0.10  # Default to 10Hz (100ms)

        roll, pitch, yaw = float(self.x[6, 0]), float(self.x[7, 0]), float(self.x[8, 0])

        # 1. Update Euler angles using angular rates from gyroscope
        gx, gy, gz = gyro_body[0], gyro_body[1], gyro_body[2]
        self.x[6, 0] += gx * dt
        self.x[7, 0] += gy * dt
        self.x[8, 0] += gz * dt

        # Wrap yaw between -pi and pi
        self.x[8, 0] = (self.x[8, 0] + np.pi) % (2 * np.pi) - np.pi

        # 2. Transform body acceleration into world navigation frame (gravity-free)
        a_nav = body_to_nav_acceleration(accel_body, roll, pitch, yaw)

        # Zero velocity update (ZUPT) heuristic for pedestrian standing still:
        accel_mag = np.linalg.norm(accel_body)
        gyro_mag = np.linalg.norm(gyro_body)
        if abs(accel_mag - GRAVITY) < 0.25 and gyro_mag < 0.05:
            # Device stationary: decay velocities to 0
            self.x[3:6, 0] *= 0.7
            a_nav = np.zeros(3)

        # 3. Numerical Integration for Velocity and Position
        # v = v + a * dt
        self.x[3, 0] += a_nav[0] * dt
        self.x[4, 0] += a_nav[1] * dt
        self.x[5, 0] += a_nav[2] * dt

        # p = p + v * dt + 0.5 * a * dt^2
        self.x[0, 0] += self.x[3, 0] * dt + 0.5 * a_nav[0] * (dt ** 2)
        self.x[1, 0] += self.x[4, 0] * dt + 0.5 * a_nav[1] * (dt ** 2)
        self.x[2, 0] += self.x[5, 0] * dt + 0.5 * a_nav[2] * (dt ** 2)

        # 4. Covariance Propagation
        F = np.eye(9)
        F[0:3, 3:6] = np.eye(3) * dt
        self.P = F @ self.P @ F.T + self.Q

    def update_magnetometer(self, mag_body: np.ndarray):
        """Measurement update using tilt-compensated compass heading."""
        roll, pitch = float(self.x[6, 0]), float(self.x[7, 0])
        mag_yaw = calculate_tilt_compensated_heading(mag_body, roll, pitch)

        # Measurement model for yaw
        H = np.zeros((1, 9))
        H[0, 8] = 1.0

        y = np.array([[mag_yaw]]) - (H @ self.x)
        # Wrap residual
        y[0, 0] = (y[0, 0] + np.pi) % (2 * np.pi) - np.pi

        R_yaw = np.array([[0.3]])
        S = H @ self.P @ H.T + R_yaw
        K = self.P @ H.T @ np.linalg.inv(S)

        self.x = self.x + K @ y
        self.P = (np.eye(9) - K @ H) @ self.P

    def process_sample(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single IMU reading packet (at 10Hz) and return rough fused state.
        """
        current_ts = packet.get("timestamp", 0.0)
        dt = (current_ts - self.last_timestamp) if self.last_timestamp else 0.10
        # Clamp dt to reasonable bounds around 10Hz (e.g. 0.02s to 1.0s)
        dt = max(0.01, min(1.0, dt))
        self.last_timestamp = current_ts

        accel = np.array([packet.get("ax", 0.0), packet.get("ay", 0.0), packet.get("az", 0.0)])
        gyro = np.array([packet.get("gx", 0.0), packet.get("gy", 0.0), packet.get("gz", 0.0)])
        
        # Prediction step
        self.predict(accel, gyro, dt)

        # Measurement update if magnetometer data present
        if "mx" in packet and "my" in packet and "mz" in packet:
            mag = np.array([packet["mx"], packet["my"], packet["mz"]])
            if np.linalg.norm(mag) > 1e-3:
                self.update_magnetometer(mag)

        return {
            "x": float(self.x[0, 0]),
            "y": float(self.x[1, 0]),
            "z": float(self.x[2, 0]),
            "vx": float(self.x[3, 0]),
            "vy": float(self.x[4, 0]),
            "vz": float(self.x[5, 0]),
            "roll": float(self.x[6, 0]),
            "pitch": float(self.x[7, 0]),
            "yaw": float(self.x[8, 0]),
            "covariance": self.P.tolist()
        }

    def to_state_dict(self) -> Dict[str, Any]:
        """Export state for caching or serialization."""
        return {
            "x": self.x.tolist(),
            "P": self.P.tolist(),
            "last_timestamp": self.last_timestamp
        }

    @classmethod
    def from_state_dict(cls, state_dict: Dict[str, Any]) -> "IMUKalmanFilter":
        """Reconstruct filter instance from cached state dict."""
        kf = cls(
            initial_state=np.array(state_dict["x"]),
            initial_covariance=np.array(state_dict["P"])
        )
        kf.last_timestamp = state_dict.get("last_timestamp")
        return kf
