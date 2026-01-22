"""Payment domain enums."""

from enum import Enum


class PaymentStatus(str, Enum):
    """Payment status enum.

    Values must match PostgreSQL enum 'payments_payment_status_enum' created by TypeORM.
    Uses uppercase values to match database.
    """

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"  # Added for Payment MS
    COMPLETED = "COMPLETED"  # Maps to succeeded
    CANCELLED = "CANCELLED"  # Maps to canceled
    FAILED = "FAILED"  # Added for Payment MS
    REFUNDED = "REFUNDED"  # Added for Payment MS


class PaymentType(str, Enum):
    """Payment type enum."""

    RESERVATION = "reservation"
    SUBSCRIPTION = "subscription"


class Currency(str, Enum):
    """Supported currencies."""

    USD = "usd"
    EUR = "eur"
    MXN = "mxn"


class WebhookEventType(str, Enum):
    """Webhook event types for B2B partners."""

    PAYMENT_CREATED = "payment.created"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"
    RESERVATION_PAID = "reservation.paid"
