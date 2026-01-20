"""Payment DTOs for API requests/responses."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from mesaYA_payment_ms.features.payments.domain.enums import (
    PaymentStatus,
    PaymentType,
    Currency,
)


class PaymentCreateRequest(BaseModel):
    """Request to create a new payment."""

    amount: Decimal = Field(..., gt=0, description="Payment amount")
    currency: Currency = Field(default=Currency.USD, description="Currency code")
    payment_type: PaymentType = Field(
        default=PaymentType.RESERVATION, description="Type of payment"
    )

    reservation_id: UUID | None = Field(None, description="Related reservation ID")
    subscription_id: UUID | None = Field(None, description="Related subscription ID")
    user_id: UUID | None = Field(None, description="User making the payment")

    payer_email: str | None = Field(None, description="Payer email address")
    payer_name: str | None = Field(None, description="Payer full name")
    description: str | None = Field(None, max_length=500, description="Payment description")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")

    success_url: str | None = Field(None, description="Redirect URL on success")
    cancel_url: str | None = Field(None, description="Redirect URL on cancel")

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v: Any) -> Decimal:
        """Parse amount to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        return Decimal(str(v))

    @field_validator("currency", mode="before")
    @classmethod
    def parse_currency(cls, v: Any) -> str:
        """Parse currency to lowercase."""
        if isinstance(v, str):
            return v.lower()
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "amount": "25.00",
                "currency": "usd",
                "payment_type": "reservation",
                "reservation_id": "123e4567-e89b-12d3-a456-426614174000",
                "payer_email": "john@example.com",
                "payer_name": "John Doe",
                "description": "Reservation deposit for 2 guests",
            }
        }


class PaymentIntentResponse(BaseModel):
    """Response with payment intent data for frontend."""

    payment_id: UUID
    status: PaymentStatus
    provider: str
    checkout_url: str | None = None
    client_secret: str | None = None


class PaymentResponse(BaseModel):
    """Full payment response."""

    id: UUID
    amount: str
    currency: Currency
    status: PaymentStatus
    payment_type: PaymentType

    reservation_id: UUID | None = None
    subscription_id: UUID | None = None
    user_id: UUID | None = None

    provider: str
    provider_payment_id: str | None = None
    checkout_url: str | None = None

    payer_email: str | None = None
    payer_name: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "amount": "25.00",
                "currency": "usd",
                "status": "succeeded",
                "payment_type": "reservation",
                "provider": "stripe",
                "created_at": "2026-01-19T10:00:00Z",
                "updated_at": "2026-01-19T10:05:00Z",
            }
        }


class PaymentVerifyResponse(BaseModel):
    """Response from verifying a payment with the provider."""

    payment_id: UUID
    previous_status: PaymentStatus
    current_status: PaymentStatus
    synchronized: bool


class PaymentCancelResponse(BaseModel):
    """Response from canceling a payment."""

    payment_id: UUID
    status: PaymentStatus
    canceled: bool


class PaymentRefundResponse(BaseModel):
    """Response from refunding a payment."""

    payment_id: UUID
    status: PaymentStatus
    refund_id: str | None = None
    refunded: bool
    error_message: str | None = None
