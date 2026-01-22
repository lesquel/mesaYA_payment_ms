"""Payment ORM model for SQLAlchemy."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB

from mesaYA_payment_ms.shared.infrastructure.database.connection import Base
from mesaYA_payment_ms.features.payments.domain.enums import (
    PaymentStatus,
    PaymentType,
    Currency,
)


class PaymentModel(Base):
    """
    Payment ORM model.

    Maps to the 'payments' table in the shared database.

    Core columns (match TypeORM entity in mesaYA_Res):
    - payment_id (UUID, PK)
    - reservation_id (UUID, FK, nullable)
    - subscription_id (UUID, FK, nullable)
    - amount (Decimal)
    - payment_status (Enum)
    - created_at (Timestamp)
    - updated_at (Timestamp)

    Extended columns (added by Payment MS - may require migration):
    - user_id, currency, payment_type, provider, etc.
    """

    __tablename__ = "payments"

    # Primary key - matches TypeORM entity
    id = Column(
        "payment_id",
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Foreign keys - matches TypeORM entity
    reservation_id = Column(
        "reservation_id",
        PGUUID(as_uuid=True),
        nullable=True,
    )

    subscription_id = Column(
        "subscription_id",
        PGUUID(as_uuid=True),
        nullable=True,
    )

    # Payment amount - matches TypeORM entity
    amount = Column(
        Numeric(10, 2),
        nullable=False,
    )

    # Status - matches TypeORM entity (payment_status column with enum)
    # Note: The enum is created by TypeORM, we use create_type=False to avoid conflicts
    payment_status = Column(
        "payment_status",
        String(50),  # Use String to be compatible with existing enum or varchar
        nullable=False,
        default=PaymentStatus.PENDING.value,
    )

    # Timestamps - matches TypeORM entity
    created_at = Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # === Extended columns (may need migration) ===

    user_id = Column(
        "user_id",
        PGUUID(as_uuid=True),
        nullable=True,
    )

    currency = Column(
        String(3),
        nullable=True,  # Nullable for backward compatibility
        default="usd",
    )

    payment_type = Column(
        String(20),
        nullable=True,
        default="reservation",
    )

    provider = Column(
        String(50),
        nullable=True,
        default="mock",
    )

    provider_payment_id = Column(
        String(255),
        nullable=True,
    )

    checkout_url = Column(
        Text,
        nullable=True,
    )

    # Payer information (new columns)
    payer_email = Column(
        String(255),
        nullable=True,
    )

    payer_name = Column(
        String(255),
        nullable=True,
    )

    # Metadata
    description = Column(
        Text,
        nullable=True,
    )

    metadata = Column(
        JSONB,
        nullable=True,
        default=dict,
    )

    idempotency_key = Column(
        String(255),
        nullable=True,
        unique=True,
    )

    failure_reason = Column(
        Text,
        nullable=True,
    )

    def to_domain(self) -> "Payment":
        """Convert ORM model to domain entity."""
        from mesaYA_payment_ms.features.payments.domain.entities import Payment

        # Handle currency - may be stored as string
        try:
            currency = (
                Currency(self.currency.lower()) if self.currency else Currency.USD
            )
        except ValueError:
            currency = Currency.USD

        # Handle status - may be stored as string (enum value) or enum
        try:
            if isinstance(self.payment_status, PaymentStatus):
                status = self.payment_status
            else:
                status = PaymentStatus(
                    self.payment_status.lower() if self.payment_status else "pending"
                )
        except ValueError:
            status = PaymentStatus.PENDING

        return Payment(
            id=self.id,
            amount=Decimal(str(self.amount)),
            currency=currency,
            status=status,
            payment_type=(
                PaymentType(self.payment_type)
                if self.payment_type
                else PaymentType.RESERVATION
            ),
            reservation_id=self.reservation_id,
            subscription_id=self.subscription_id,
            user_id=self.user_id,
            provider=self.provider or "mock",
            provider_payment_id=self.provider_payment_id,
            checkout_url=self.checkout_url,
            payer_email=self.payer_email,
            payer_name=self.payer_name,
            description=self.description,
            metadata=self.metadata or {},
            idempotency_key=self.idempotency_key,
            failure_reason=self.failure_reason,
            created_at=self.created_at or datetime.utcnow(),
            updated_at=self.updated_at or datetime.utcnow(),
        )

    @classmethod
    def from_domain(cls, payment: "Payment") -> "PaymentModel":
        """Create ORM model from domain entity."""
        # Handle status - convert enum to string value
        status_value = (
            payment.status.value
            if isinstance(payment.status, PaymentStatus)
            else str(payment.status)
        )

        return cls(
            id=payment.id,
            reservation_id=payment.reservation_id,
            subscription_id=payment.subscription_id,
            user_id=payment.user_id,
            amount=payment.amount,
            currency=(
                payment.currency.value
                if isinstance(payment.currency, Currency)
                else str(payment.currency)
            ),
            payment_status=status_value,
            payment_type=(
                payment.payment_type.value
                if isinstance(payment.payment_type, PaymentType)
                else str(payment.payment_type)
            ),
            provider=payment.provider,
            provider_payment_id=payment.provider_payment_id,
            checkout_url=payment.checkout_url,
            payer_email=payment.payer_email,
            payer_name=payment.payer_name,
            description=payment.description,
            metadata=payment.metadata,
            idempotency_key=payment.idempotency_key,
            failure_reason=payment.failure_reason,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )


# Import Payment for type hints
from mesaYA_payment_ms.features.payments.domain.entities import Payment
