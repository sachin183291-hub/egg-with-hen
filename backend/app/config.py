"""
Application configuration using Pydantic Settings.
All values can be overridden via environment variables or .env file.
"""
from typing import List, Optional
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # App
    APP_NAME: str = "GioTag Evidence System"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite:///./giotag.db"

    # Security
    SECRET_KEY: str = "changeme-super-secret-jwt-key-minimum-32-characters-long"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    # Storage
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "./uploads"
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    SUPABASE_BUCKET: str = "evidence-images"

    # AI
    AI_ENABLED: bool = True
    AI_MODEL_TYPE: str = "opencv"
    AI_MODEL_PATH: Optional[str] = None

    # OpenAI Vision
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    
    # Gemini Vision
    GEMINI_API_KEY: Optional[str] = None
    
    # Options: openai | gemini | yolo
    DETECTOR_PROVIDER: str = "gemini"
    OPENAI_MAX_IMAGE_SIZE_MB: int = 20

    # Blockchain
    BLOCKCHAIN_MODE: str = "local"
    LOCAL_LEDGER_PATH: str = "./app/blockchain/ledger_data.json"

    # File Upload
    MAX_FILE_SIZE_MB: int = 15
    ALLOWED_MIME_TYPES: str = "image/jpeg,image/jpg,image/png,image/webp"

    @property
    def allowed_mime_types_list(self) -> List[str]:
        return [m.strip() for m in self.ALLOWED_MIME_TYPES.split(",")]

    # GPS
    GPS_ACCURACY_THRESHOLD_METERS: float = 50.0

    # Demo
    SEED_DEMO_DATA: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
