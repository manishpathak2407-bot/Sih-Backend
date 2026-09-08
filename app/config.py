from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "SIH Dead Reckoning Backend"
    VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # Security & JWT
    SECRET_KEY: str = "sih_super_secure_dr_jwt_secret_key_2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Caching Layer (Redis with in-memory fallback)
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL_LIVE_SEC: int = 3600             # 1 hour for device live position
    REDIS_TTL_ML_CACHE_SEC: int = 1800         # 30 mins for window hash cache
    REDIS_TTL_CALIBRATION_SEC: int = 86400     # 24 hours for calibration constants

    # Storage Layer (PostgreSQL/TimescaleDB or SQLite fallback)
    DATABASE_URL: str = "sqlite+aiosqlite:///./sih_trajectories.db"

    # IMU & Queue Configuration
    IMU_SAMPLING_RATE_HZ: float = 50.0
    WINDOW_SIZE: int = 50                      # 1 second window at 50Hz
    BACKLOG_CHUNK_SIZE: int = 50               # Max packets to yield per backlog chunk
    MAX_QUEUE_SIZE: int = 50000

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
