"""Application settings using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8003
    debug: bool = True
    environment: Literal["development", "staging", "production"] = "development"

    # Database
    database_url: str

    # Payment Provider
    payment_provider: Literal["stripe", "mercadopago", "mock"] = "mock"

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # MercadoPago
    mercadopago_access_token: str = ""
    mercadopago_public_key: str = ""

    # Mock Provider
    mock_webhook_secret: str = "whsec_mock_development_secret"

    # Partner Webhooks
    partner_webhook_timeout: int = 10
    partner_max_retries: int = 3

    # URLs
    frontend_url: str = "http://localhost:4200"
    success_url: str = "http://localhost:4200/payment/success"
    cancel_url: str = "http://localhost:4200/payment/cancel"

    # Internal Services
    mesa_ya_res_url: str = "http://localhost:3000"
    n8n_webhook_url: str = "http://localhost:5678/webhook"

    # Security
    hmac_secret_prefix: str = "whsec_"

    # CORS
    cors_origins: list[str] = ["http://localhost:4200", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
