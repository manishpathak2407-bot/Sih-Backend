# 10Hz Dead Reckoning Backend Engine - SIH 2026
import numpy as np
from typing import Tuple

GRAVITY = 9.80665

def euler_to_rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """
    Computes 3x3 Rotation matrix R from body frame to navigation frame (NED: North-East-Down).
    roll (phi): rotation about X
    pitch (theta): rotation about Y
    yaw (psi): rotation about Z
    """
    cr = np.cos(roll)
    sr = np.sin(roll)
    cp = np.cos(pitch)
    sp = np.sin(pitch)
    cy = np.cos(yaw)
    sy = np.sin(yaw)

    R_x = np.array([
        [1, 0, 0],
        [0, cr, -sr],
        [0, sr, cr]
    ])

    R_y = np.array([
        [cp, 0, sp],
        [0, 1, 0],
        [-sp, 0, cp]
    ])

    R_z = np.array([
        [cy, -sy, 0],
        [sy, cy, 0],
        [0, 0, 1]
    ])

    return R_z @ R_y @ R_x

def body_to_nav_acceleration(accel_body: np.ndarray, roll: float, pitch: float, yaw: float) -> np.ndarray:
    """
    Rotates body acceleration into navigation frame and removes Earth gravity (9.81 m/s²).
    """
    R = euler_to_rotation_matrix(roll, pitch, yaw)
    accel_nav = R @ accel_body
    # Subtract gravity in the vertical Z-axis (pointing down)
    accel_nav[2] -= GRAVITY
    return accel_nav

def calculate_tilt_compensated_heading(mag_body: np.ndarray, roll: float, pitch: float) -> float:
    """
    Calculates compass heading from 3-axis magnetometer compensated for phone tilt (roll & pitch).
    """
    mx, my, mz = mag_body[0], mag_body[1], mag_body[2]
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)

    # De-tilt magnetometer readings into horizontal plane
    xh = mx * cp + my * sr * sp + mz * cr * sp
    yh = my * cr - mz * sr

    heading = np.arctan2(-yh, xh)
    return float(heading)

