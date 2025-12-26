"""
Application configuration using Pydantic Settings.
All configuration is loaded from environment variables (12-factor app).
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === Application ===
    app_name: str = Field(default="MIDA OCR API", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    environment: str = Field(default="development", description="Environment: development, staging, production")
    debug: bool = Field(default=False, description="Enable debug mode")

    # === Server ===
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # === Database (single source of truth) ===
    database_url: Optional[str] = Field(default=None, description="Database connection URL")

    # === Azure Document Intelligence ===
    azure_di_endpoint: str = Field(default="", description="Azure Document Intelligence endpoint")
    azure_di_key: str = Field(default="", description="Azure Document Intelligence API key")

    # === CORS ===
    cors_origins: str = Field(default="*", description="Comma-separated list of allowed CORS origins")

    # === Logging ===
    log_level: str = Field(default="INFO", description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    log_format: str = Field(default="json", description="Log format: json or text")

    # === MIDA API Client ===
    # Used by converter service to fetch certificate data from MIDA backend
    mida_api_base_url: Optional[str] = Field(
        default=None,
        description="MIDA API base URL (e.g., http://mida-service:8000)"
    )
    mida_api_timeout_seconds: int = Field(
        default=10,
        description="Timeout in seconds for MIDA API requests"
    )
    mida_api_cache_ttl_seconds: int = Field(
        default=60,
        description="TTL in seconds for MIDA API response caching"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Use dependency injection in FastAPI routes: settings = Depends(get_settings)
    """
    return Settings()
