"""Payment provider factory - Dependency injection."""

from functools import lru_cache

from mesaYA_payment_ms.features.payments.application.ports import PaymentProviderPort
from mesaYA_payment_ms.features.payments.infrastructure.adapters import (
    MockPaymentAdapter,
    StripePaymentAdapter,
)
from mesaYA_payment_ms.shared.core.settings import get_settings


@lru_cache
def get_payment_provider() -> PaymentProviderPort:
    """
    Get the payment provider based on configuration.

    Factory function for dependency injection.
    """
    settings = get_settings()

    match settings.payment_provider:
        case "stripe":
            return StripePaymentAdapter()
        case "mock":
            return MockPaymentAdapter()
        case _:
            # Default to mock for unknown providers
            return MockPaymentAdapter()
