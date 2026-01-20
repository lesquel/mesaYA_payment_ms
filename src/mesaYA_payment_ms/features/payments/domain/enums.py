"""Payment domain enums."""

from enum import Enum


class PaymentStatus(str, Enum):
    """Payment status enum."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"


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
