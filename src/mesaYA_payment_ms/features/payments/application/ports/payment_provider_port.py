"""Payment provider port (interface) - Adapter Pattern."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from mesaYA_payment_ms.features.payments.domain.enums import PaymentStatus, Currency


@dataclass
class PaymentIntentRequest:
    """Request to create a payment intent."""

    amount: Decimal
    currency: Currency
    description: str | None = None
    metadata: dict[str, Any] | None = None
    success_url: str | None = None
    cancel_url: str | None = None
    payer_email: str | None = None


@dataclass
class PaymentIntentResult:
    """Result from creating a payment intent."""

    provider_payment_id: str
    client_secret: str | None = None
    checkout_url: str | None = None
    status: PaymentStatus = PaymentStatus.PENDING


@dataclass
class RefundResult:
    """Result from a refund operation."""

    success: bool
    refund_id: str | None = None
    error_message: str | None = None


class PaymentProviderPort(ABC):
    """
    Abstract interface for payment providers (Adapter Pattern).

    Implementations:
    - StripeAdapter
    - MercadoPagoAdapter
    - MockAdapter (for development)
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider name."""
        pass

    @abstractmethod
    async def create_payment_intent(
        self, request: PaymentIntentRequest
    ) -> PaymentIntentResult:
        """
        Create a payment intent with the provider.

        Returns checkout URL or client secret for frontend.
        """
        pass

    @abstractmethod
    async def verify_payment(self, provider_payment_id: str) -> PaymentStatus:
        """
        Verify the current status of a payment with the provider.

        Used after returning from checkout to sync state.
        """
        pass

    @abstractmethod
    async def cancel_payment(self, provider_payment_id: str) -> bool:
        """
        Cancel a pending payment.

        Returns True if successfully canceled.
        """
        pass

    @abstractmethod
    async def refund_payment(
        self, provider_payment_id: str, amount: Decimal | None = None
    ) -> RefundResult:
        """
        Refund a completed payment.

        If amount is None, full refund is performed.
        """
        pass

    @abstractmethod
    def verify_webhook_signature(
        self, payload: bytes, signature: str
    ) -> bool:
        """
        Verify the signature of an incoming webhook.

        Returns True if signature is valid.
        """
        pass
