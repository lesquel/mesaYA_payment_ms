"""Partner DTOs for API requests/responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from mesaYA_payment_ms.features.partners.domain.entities import (
    PartnerStatus,
    WebhookEventType,
)


class PartnerRegisterRequest(BaseModel):
    """Request to register a new B2B partner."""

    name: str = Field(..., min_length=2, max_length=100, description="Partner name")
    webhook_url: HttpUrl = Field(..., description="URL to receive webhooks")
    events: list[WebhookEventType] = Field(
        ..., min_length=1, description="Events to subscribe to"
    )
    description: str | None = Field(None, max_length=500, description="Partner description")
    contact_email: str | None = Field(None, description="Contact email")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Hotel Partner",
                "webhook_url": "https://partner.com/webhooks/mesaya",
                "events": ["payment.succeeded", "reservation.confirmed"],
                "description": "Integration with Hotel booking system",
                "contact_email": "tech@partner.com",
            }
        }


class PartnerUpdateRequest(BaseModel):
    """Request to update a partner."""

    name: str | None = Field(None, min_length=2, max_length=100)
    webhook_url: HttpUrl | None = None
    events: list[WebhookEventType] | None = None
    description: str | None = Field(None, max_length=500)
    contact_email: str | None = None
    status: PartnerStatus | None = None


class PartnerRegisterResponse(BaseModel):
    """Response after registering a partner - includes secret."""

    id: UUID
    name: str
    webhook_url: str
    events: list[WebhookEventType]
    status: PartnerStatus
    secret: str = Field(..., description="HMAC secret - Store securely! Only shown once.")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Hotel Partner",
                "webhook_url": "https://partner.com/webhooks/mesaya",
                "events": ["payment.succeeded", "reservation.confirmed"],
                "status": "active",
                "secret": "whsec_abc123def456...",
            }
        }


class PartnerResponse(BaseModel):
    """Partner response without secret."""

    id: UUID
    name: str
    webhook_url: str
    events: list[WebhookEventType]
    status: PartnerStatus
    description: str | None = None
    contact_email: str | None = None
    total_webhooks_sent: int = 0
    consecutive_failures: int = 0
    last_webhook_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PartnerSecretRotateResponse(BaseModel):
    """Response after rotating a partner's secret."""

    id: UUID
    new_secret: str = Field(..., description="New HMAC secret")
    message: str = "Secret rotated successfully. Old secret is now invalid."


class TestWebhookRequest(BaseModel):
    """Request to send a test webhook to a partner."""

    event_type: WebhookEventType = Field(
        default=WebhookEventType.PAYMENT_SUCCEEDED,
        description="Event type to simulate",
    )
    payload: dict | None = Field(None, description="Custom payload (optional)")

    class Config:
        json_schema_extra = {
            "example": {
                "event_type": "payment.succeeded",
                "payload": {
                    "payment_id": "test-123",
                    "amount": "25.00",
                    "currency": "usd",
                },
            }
        }


class TestWebhookResponse(BaseModel):
    """Response from sending a test webhook."""

    success: bool
    message: str
    payload_sent: dict
    status_code: int | None = None
    response_body: str | None = None
