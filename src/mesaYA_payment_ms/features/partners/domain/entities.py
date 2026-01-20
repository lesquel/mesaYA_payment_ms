"""Partner domain entity and enums."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4
import secrets


class PartnerStatus(str, Enum):
    """Partner status enum."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class WebhookEventType(str, Enum):
    """Webhook event types for B2B partners."""

    # Payment events
    PAYMENT_CREATED = "payment.created"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"

    # Reservation events
    RESERVATION_CREATED = "reservation.created"
    RESERVATION_CONFIRMED = "reservation.confirmed"
    RESERVATION_CANCELLED = "reservation.cancelled"
    RESERVATION_COMPLETED = "reservation.completed"
    RESERVATION_PAID = "reservation.paid"

    # Wildcard
    ALL = "*"


@dataclass
class Partner:
    """B2B Partner entity for webhook integration."""

    id: UUID
    name: str
    webhook_url: str
    events: list[WebhookEventType]
    secret: str
    status: PartnerStatus = PartnerStatus.ACTIVE

    description: str | None = None
    contact_email: str | None = None

    # Statistics
    total_webhooks_sent: int = 0
    consecutive_failures: int = 0
    last_webhook_at: datetime | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def create(
        cls,
        name: str,
        webhook_url: str,
        events: list[WebhookEventType],
        description: str | None = None,
        contact_email: str | None = None,
    ) -> "Partner":
        """Create a new partner with a generated secret."""
        secret = f"whsec_{secrets.token_hex(24)}"
        return cls(
            id=uuid4(),
            name=name,
            webhook_url=webhook_url,
            events=events,
            secret=secret,
            description=description,
            contact_email=contact_email,
        )

    def regenerate_secret(self) -> str:
        """Regenerate the webhook secret."""
        self.secret = f"whsec_{secrets.token_hex(24)}"
        self.updated_at = datetime.utcnow()
        return self.secret

    def is_subscribed_to(self, event: WebhookEventType) -> bool:
        """Check if partner is subscribed to an event type."""
        if WebhookEventType.ALL in self.events:
            return True
        return event in self.events

    def record_webhook_success(self) -> None:
        """Record a successful webhook delivery."""
        self.total_webhooks_sent += 1
        self.consecutive_failures = 0
        self.last_webhook_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def record_webhook_failure(self) -> None:
        """Record a failed webhook delivery."""
        self.consecutive_failures += 1
        self.updated_at = datetime.utcnow()

        # Auto-suspend after too many failures
        if self.consecutive_failures >= 10:
            self.status = PartnerStatus.SUSPENDED

    def activate(self) -> None:
        """Activate the partner."""
        self.status = PartnerStatus.ACTIVE
        self.consecutive_failures = 0
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        """Deactivate the partner."""
        self.status = PartnerStatus.INACTIVE
        self.updated_at = datetime.utcnow()

    def suspend(self) -> None:
        """Suspend the partner."""
        self.status = PartnerStatus.SUSPENDED
        self.updated_at = datetime.utcnow()

    def to_dict(self, include_secret: bool = False) -> dict[str, Any]:
        """Convert to dictionary."""
        data = {
            "id": str(self.id),
            "name": self.name,
            "webhook_url": self.webhook_url,
            "events": [e.value for e in self.events],
            "status": self.status.value,
            "description": self.description,
            "contact_email": self.contact_email,
            "total_webhooks_sent": self.total_webhooks_sent,
            "consecutive_failures": self.consecutive_failures,
            "last_webhook_at": self.last_webhook_at.isoformat() if self.last_webhook_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_secret:
            data["secret"] = self.secret
        return data
