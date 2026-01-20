"""Mock Payment Provider Adapter - For development and testing."""

import hashlib
import hmac
import secrets
import time
from decimal import Decimal
from typing import Any

from mesaYA_payment_ms.features.payments.application.ports import (
    PaymentProviderPort,
    PaymentIntentRequest,
    PaymentIntentResult,
    RefundResult,
)
from mesaYA_payment_ms.features.payments.domain.enums import PaymentStatus
from mesaYA_payment_ms.shared.core.settings import get_settings


class MockPaymentAdapter(PaymentProviderPort):
    """
    Mock payment provider for development and testing.

    Simulates payment flows without external API calls.
    Webhooks can be triggered manually via /api/webhooks/mock endpoint.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._pending_payments: dict[str, dict[str, Any]] = {}

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "mock"

    async def create_payment_intent(
        self, request: PaymentIntentRequest
    ) -> PaymentIntentResult:
        """
        Create a mock payment intent.

        Returns a fake checkout URL that can be used for testing.
        """
        # Generate mock IDs
        mock_payment_id = f"mock_pi_{secrets.token_hex(12)}"
        mock_client_secret = f"mock_secret_{secrets.token_hex(16)}"

        # Build checkout URL
        checkout_url = (
            f"{self._settings.frontend_url}/payment/mock-checkout"
            f"?payment_id={mock_payment_id}"
            f"&amount={request.amount}"
            f"&currency={request.currency.value}"
        )

        # Store payment for later verification
        self._pending_payments[mock_payment_id] = {
            "amount": str(request.amount),
            "currency": request.currency.value,
            "status": PaymentStatus.PENDING.value,
            "created_at": time.time(),
        }

        return PaymentIntentResult(
            provider_payment_id=mock_payment_id,
            client_secret=mock_client_secret,
            checkout_url=checkout_url,
            status=PaymentStatus.PENDING,
        )

    async def verify_payment(self, provider_payment_id: str) -> PaymentStatus:
        """
        Verify the status of a mock payment.

        By default returns SUCCEEDED for testing convenience.
        """
        if provider_payment_id in self._pending_payments:
            status = self._pending_payments[provider_payment_id].get("status", "succeeded")
            return PaymentStatus(status)
        # For unknown payments, assume succeeded (for testing)
        return PaymentStatus.SUCCEEDED

    async def cancel_payment(self, provider_payment_id: str) -> bool:
        """Cancel a mock payment."""
        if provider_payment_id in self._pending_payments:
            self._pending_payments[provider_payment_id]["status"] = PaymentStatus.CANCELED.value
            return True
        return True  # Allow canceling unknown payments in mock

    async def refund_payment(
        self, provider_payment_id: str, amount: Decimal | None = None
    ) -> RefundResult:
        """Refund a mock payment."""
        refund_id = f"mock_re_{secrets.token_hex(8)}"

        if provider_payment_id in self._pending_payments:
            self._pending_payments[provider_payment_id]["status"] = PaymentStatus.REFUNDED.value

        return RefundResult(
            success=True,
            refund_id=refund_id,
        )

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify mock webhook signature.

        Expected format: t=<timestamp>,v1=<signature>
        """
        try:
            parts = dict(part.split("=", 1) for part in signature.split(","))
            timestamp = parts.get("t", "")
            provided_sig = parts.get("v1", "")

            # Check timestamp is recent (within 5 minutes)
            if timestamp:
                ts = int(timestamp)
                now = int(time.time())
                if abs(now - ts) > 300:
                    return False

            # Compute expected signature
            signed_payload = f"{timestamp}.{payload.decode()}"
            expected_sig = hmac.new(
                self._settings.mock_webhook_secret.encode(),
                signed_payload.encode(),
                hashlib.sha256,
            ).hexdigest()

            # Timing-safe comparison
            return hmac.compare_digest(expected_sig, provided_sig)

        except (ValueError, KeyError):
            return False

    def generate_webhook_signature(self, payload: str) -> str:
        """
        Generate a webhook signature for testing.

        Useful for simulating webhook calls in development.
        """
        timestamp = str(int(time.time()))
        signed_payload = f"{timestamp}.{payload}"
        signature = hmac.new(
            self._settings.mock_webhook_secret.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp},v1={signature}"

    def simulate_payment_success(self, provider_payment_id: str) -> None:
        """Simulate a successful payment (for testing)."""
        if provider_payment_id in self._pending_payments:
            self._pending_payments[provider_payment_id]["status"] = PaymentStatus.SUCCEEDED.value

    def simulate_payment_failure(self, provider_payment_id: str) -> None:
        """Simulate a failed payment (for testing)."""
        if provider_payment_id in self._pending_payments:
            self._pending_payments[provider_payment_id]["status"] = PaymentStatus.FAILED.value
