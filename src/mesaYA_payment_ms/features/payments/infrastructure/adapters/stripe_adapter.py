"""Stripe Payment Provider Adapter."""

import hashlib
import hmac
import time
from decimal import Decimal

import stripe
from stripe import PaymentIntent

from mesaYA_payment_ms.features.payments.application.ports import (
    PaymentProviderPort,
    PaymentIntentRequest,
    PaymentIntentResult,
    RefundResult,
)
from mesaYA_payment_ms.features.payments.domain.enums import PaymentStatus
from mesaYA_payment_ms.shared.core.settings import get_settings
from mesaYA_payment_ms.shared.domain.exceptions import PaymentProviderError


class StripePaymentAdapter(PaymentProviderPort):
    """
    Stripe payment provider adapter.

    Integrates with Stripe Checkout for payment processing.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        stripe.api_key = self._settings.stripe_secret_key

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "stripe"

    async def create_payment_intent(
        self, request: PaymentIntentRequest
    ) -> PaymentIntentResult:
        """
        Create a Stripe Checkout Session.

        Returns a checkout URL for redirecting the user.
        """
        try:
            # Convert Decimal to cents (Stripe uses smallest currency unit)
            amount_cents = int(request.amount * 100)

            # Create Checkout Session
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price_data": {
                            "currency": request.currency.value,
                            "unit_amount": amount_cents,
                            "product_data": {
                                "name": request.description or "MesaYA Payment",
                            },
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url=request.success_url or self._settings.success_url,
                cancel_url=request.cancel_url or self._settings.cancel_url,
                customer_email=request.payer_email,
                metadata=request.metadata or {},
            )

            return PaymentIntentResult(
                provider_payment_id=session.id,
                client_secret=None,  # Using Checkout, not Elements
                checkout_url=session.url,
                status=PaymentStatus.PENDING,
            )

        except stripe.error.StripeError as e:
            raise PaymentProviderError("stripe", str(e)) from e

    async def verify_payment(self, provider_payment_id: str) -> PaymentStatus:
        """
        Verify the status of a Stripe payment.

        Retrieves the Checkout Session and maps status.
        """
        try:
            session = stripe.checkout.Session.retrieve(provider_payment_id)

            status_map = {
                "open": PaymentStatus.PENDING,
                "complete": PaymentStatus.SUCCEEDED,
                "expired": PaymentStatus.CANCELED,
            }

            return status_map.get(session.status, PaymentStatus.PENDING)

        except stripe.error.StripeError as e:
            raise PaymentProviderError("stripe", str(e)) from e

    async def cancel_payment(self, provider_payment_id: str) -> bool:
        """
        Cancel a Stripe Checkout Session.

        Note: Only open sessions can be expired.
        """
        try:
            stripe.checkout.Session.expire(provider_payment_id)
            return True
        except stripe.error.InvalidRequestError:
            # Session may already be completed or expired
            return False
        except stripe.error.StripeError as e:
            raise PaymentProviderError("stripe", str(e)) from e

    async def refund_payment(
        self, provider_payment_id: str, amount: Decimal | None = None
    ) -> RefundResult:
        """
        Refund a Stripe payment.

        Requires the Payment Intent ID from the completed session.
        """
        try:
            # Get the session to find the payment intent
            session = stripe.checkout.Session.retrieve(provider_payment_id)
            payment_intent_id = session.payment_intent

            if not payment_intent_id:
                return RefundResult(
                    success=False,
                    error_message="No payment intent found for this session",
                )

            # Create refund
            refund_params: dict = {"payment_intent": payment_intent_id}
            if amount is not None:
                refund_params["amount"] = int(amount * 100)

            refund = stripe.Refund.create(**refund_params)

            return RefundResult(
                success=True,
                refund_id=refund.id,
            )

        except stripe.error.StripeError as e:
            return RefundResult(
                success=False,
                error_message=str(e),
            )

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Stripe webhook signature.

        Uses the Stripe-Signature header format.
        """
        try:
            stripe.Webhook.construct_event(
                payload,
                signature,
                self._settings.stripe_webhook_secret,
            )
            return True
        except (stripe.error.SignatureVerificationError, ValueError):
            return False

    def _map_payment_intent_status(self, intent: PaymentIntent) -> PaymentStatus:
        """Map Stripe PaymentIntent status to our PaymentStatus."""
        status_map = {
            "requires_payment_method": PaymentStatus.PENDING,
            "requires_confirmation": PaymentStatus.PENDING,
            "requires_action": PaymentStatus.PROCESSING,
            "processing": PaymentStatus.PROCESSING,
            "requires_capture": PaymentStatus.PROCESSING,
            "canceled": PaymentStatus.CANCELED,
            "succeeded": PaymentStatus.SUCCEEDED,
        }
        return status_map.get(intent.status, PaymentStatus.PENDING)
