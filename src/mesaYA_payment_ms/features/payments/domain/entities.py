"""Payment domain entity."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from mesaYA_payment_ms.features.payments.domain.enums import PaymentStatus, PaymentType, Currency


@dataclass
class Payment:
    """Payment domain entity."""

    id: UUID
    amount: Decimal
    currency: Currency
    status: PaymentStatus
    payment_type: PaymentType

    # Related IDs
    reservation_id: UUID | None = None
    subscription_id: UUID | None = None
    user_id: UUID | None = None

    # Provider data
    provider: str = "mock"
    provider_payment_id: str | None = None
    checkout_url: str | None = None

    # Payer info
    payer_email: str | None = None
    payer_name: str | None = None

    # Metadata
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    failure_reason: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def create(
        cls,
        amount: Decimal,
        currency: Currency,
        payment_type: PaymentType,
        provider: str = "mock",
        reservation_id: UUID | None = None,
        subscription_id: UUID | None = None,
        user_id: UUID | None = None,
        payer_email: str | None = None,
        payer_name: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> "Payment":
        """Create a new payment in pending status."""
        return cls(
            id=uuid4(),
            amount=amount,
            currency=currency,
            status=PaymentStatus.PENDING,
            payment_type=payment_type,
            provider=provider,
            reservation_id=reservation_id,
            subscription_id=subscription_id,
            user_id=user_id,
            payer_email=payer_email,
            payer_name=payer_name,
            description=description,
            metadata=metadata or {},
            idempotency_key=idempotency_key,
        )

    def mark_processing(self, provider_payment_id: str, checkout_url: str | None = None) -> None:
        """Mark payment as processing with provider data."""
        self.status = PaymentStatus.PROCESSING
        self.provider_payment_id = provider_payment_id
        self.checkout_url = checkout_url
        self.updated_at = datetime.utcnow()

    def mark_succeeded(self) -> None:
        """Mark payment as succeeded."""
        self.status = PaymentStatus.SUCCEEDED
        self.updated_at = datetime.utcnow()

    def mark_failed(self, reason: str | None = None) -> None:
        """Mark payment as failed."""
        self.status = PaymentStatus.FAILED
        self.failure_reason = reason
        self.updated_at = datetime.utcnow()

    def mark_canceled(self) -> None:
        """Mark payment as canceled."""
        self.status = PaymentStatus.CANCELED
        self.updated_at = datetime.utcnow()

    def mark_refunded(self) -> None:
        """Mark payment as refunded."""
        self.status = PaymentStatus.REFUNDED
        self.updated_at = datetime.utcnow()

    def can_be_canceled(self) -> bool:
        """Check if payment can be canceled."""
        return self.status in (PaymentStatus.PENDING, PaymentStatus.PROCESSING)

    def can_be_refunded(self) -> bool:
        """Check if payment can be refunded."""
        return self.status == PaymentStatus.SUCCEEDED

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "amount": str(self.amount),
            "currency": self.currency.value,
            "status": self.status.value,
            "payment_type": self.payment_type.value,
            "reservation_id": str(self.reservation_id) if self.reservation_id else None,
            "subscription_id": str(self.subscription_id) if self.subscription_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "provider": self.provider,
            "provider_payment_id": self.provider_payment_id,
            "checkout_url": self.checkout_url,
            "payer_email": self.payer_email,
            "payer_name": self.payer_name,
            "description": self.description,
            "metadata": self.metadata,
            "idempotency_key": self.idempotency_key,
            "failure_reason": self.failure_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
