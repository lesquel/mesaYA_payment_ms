"""Webhook API router - Handles incoming webhooks from providers and partners."""

import hashlib
import hmac
import json
import time
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, Request

from mesaYA_payment_ms.features.payments.application.ports import PaymentProviderPort
from mesaYA_payment_ms.features.payments.domain.entities import Payment
from mesaYA_payment_ms.features.payments.domain.enums import (
    PaymentStatus,
    PaymentType,
    Currency,
)
from mesaYA_payment_ms.features.payments.infrastructure.provider_factory import (
    get_payment_provider,
)
from mesaYA_payment_ms.features.payments.infrastructure.adapters.mock_adapter import (
    MockPaymentAdapter,
)
from mesaYA_payment_ms.features.partners.domain.entities import (
    WebhookEventType,
    PartnerStatus,
)
from mesaYA_payment_ms.shared.core.settings import get_settings
from mesaYA_payment_ms.shared.domain.exceptions import WebhookVerificationError
from mesaYA_payment_ms.shared.presentation.api_response import APIResponse

router = APIRouter()


# Import the stores from payments and partners routers
# This is needed to access the in-memory storage
def get_payments_store():
    """Get payments store from payments router."""
    from mesaYA_payment_ms.features.payments.presentation.router import _payments_store

    return _payments_store


def get_partners_store():
    """Get partners store from partners router."""
    from mesaYA_payment_ms.features.partners.presentation.router import _partners_store

    return _partners_store


def get_provider() -> PaymentProviderPort:
    """Dependency for getting the payment provider."""
    return get_payment_provider()


async def send_partner_webhooks(
    event_type: WebhookEventType, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    Send webhooks to all registered partners subscribed to the event.

    Args:
        event_type: The webhook event type
        payload: The event data payload

    Returns:
        List of webhook results with partner info and status
    """
    partners_store = get_partners_store()
    results = []

    for partner in partners_store.values():
        # Skip if partner is not active
        if partner.status != PartnerStatus.ACTIVE:
            print(f"⏭️ Skipping inactive partner: {partner.name}")
            continue

        # Skip if partner is not subscribed to this event
        if not partner.is_subscribed_to(event_type):
            print(f"⏭️ Partner {partner.name} not subscribed to {event_type}")
            continue

        # Build payload with event info
        webhook_payload = {
            "event": event_type.value,
            "timestamp": datetime.utcnow().isoformat(),
            **payload,
        }

        payload_json = json.dumps(webhook_payload)

        # Generate HMAC signature
        timestamp = str(int(time.time()))
        signed_payload = f"{timestamp}.{payload_json}"
        signature = hmac.new(
            partner.secret.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        webhook_signature = f"t={timestamp},v1={signature}"

        # Send webhook
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    partner.webhook_url,
                    content=payload_json,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": webhook_signature,
                        "X-Partner-Id": str(partner.id),
                    },
                )

                if response.status_code < 300:
                    print(f"✅ Webhook sent to {partner.name}: {event_type}")
                    partner.record_webhook_success()
                    results.append(
                        {
                            "partner_id": str(partner.id),
                            "partner_name": partner.name,
                            "status": "success",
                            "status_code": response.status_code,
                        }
                    )
                else:
                    print(
                        f"⚠️ Webhook to {partner.name} returned {response.status_code}"
                    )
                    partner.record_webhook_failure()
                    results.append(
                        {
                            "partner_id": str(partner.id),
                            "partner_name": partner.name,
                            "status": "failed",
                            "status_code": response.status_code,
                            "error": response.text[:200],
                        }
                    )

        except httpx.TimeoutException:
            print(f"⏱️ Webhook timeout for {partner.name}")
            partner.record_webhook_failure()
            results.append(
                {
                    "partner_id": str(partner.id),
                    "partner_name": partner.name,
                    "status": "timeout",
                    "error": "Request timeout",
                }
            )
        except httpx.RequestError as e:
            print(f"❌ Webhook error for {partner.name}: {e}")
            partner.record_webhook_failure()
            results.append(
                {
                    "partner_id": str(partner.id),
                    "partner_name": partner.name,
                    "status": "error",
                    "error": str(e)[:200],
                }
            )

    return results


async def notify_n8n(event_type: str, data: dict[str, Any]) -> bool:
    """
    Send webhook notification to n8n for orchestration.

    Args:
        event_type: Type of event (e.g., payment.succeeded, payment.failed)
        data: Event data payload

    Returns:
        True if notification was sent successfully, False otherwise
    """
    settings = get_settings()
    # Use /webhook-test/ for development (works while "Listening for test event" in n8n)
    # Use /webhook/ for production (workflow must be ACTIVE)
    webhook_url = f"{settings.n8n_webhook_url}-test/payment-webhook"

    payload = {
        "event": event_type,
        "payment_id": data.get("payment_id", ""),
        "status": (
            "approved" if data.get("status") == "succeeded" else data.get("status", "")
        ),
        "amount": data.get("amount", 0),
        "currency": data.get("currency", "USD"),
        "metadata": {
            "reservation_id": data.get("reservation_id", ""),
            "service_type": data.get("service_type", "reservation"),
            "customer_email": data.get("customer_email", ""),
            "customer_name": data.get("customer_name", ""),
        },
        "source": "mesaYA_payment_ms",
        "provider": data.get("provider", "mock"),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code < 300:
                print(f"📤 n8n webhook sent successfully: {event_type}")
                return True
            else:
                print(f"⚠️ n8n webhook returned {response.status_code}: {response.text}")
                return False

    except httpx.TimeoutException:
        print(f"⏱️ n8n webhook timeout for {event_type}")
        return False
    except httpx.RequestError as e:
        print(f"❌ n8n webhook error: {e}")
        return False


@router.post(
    "/stripe",
    summary="Stripe Webhook",
    description="""
    Endpoint for receiving webhooks from Stripe.

    - Validates signature using `Stripe-Signature` header
    - Updates payment status in the database
    - Triggers webhooks to B2B partners
    - Notifies n8n for orchestration

    **Important**: Configure this URL in Stripe Dashboard.
    """,
)
async def stripe_webhook(
    request: Request,
    provider: Annotated[PaymentProviderPort, Depends(get_provider)],
    stripe_signature: Annotated[str, Header(alias="Stripe-Signature")],
) -> dict[str, str]:
    """Handle Stripe webhooks."""
    payload = await request.body()

    # Verify signature
    if not provider.verify_webhook_signature(payload, stripe_signature):
        raise WebhookVerificationError("Invalid Stripe signature")

    # Parse event
    try:
        event = json.loads(payload)
        event_type = event.get("type", "")
        data = event.get("data", {}).get("object", {})

        # Handle different event types
        if event_type == "checkout.session.completed":
            # Payment succeeded
            session_id = data.get("id")
            payment_id = data.get("metadata", {}).get("payment_id")
            print(f"✅ Payment {payment_id} completed via Stripe session {session_id}")
            # TODO: Update payment in DB, trigger partner webhooks

        elif event_type == "checkout.session.expired":
            # Payment expired/canceled
            session_id = data.get("id")
            payment_id = data.get("metadata", {}).get("payment_id")
            print(f"❌ Payment {payment_id} expired via Stripe session {session_id}")
            # TODO: Update payment status

        elif event_type == "charge.refunded":
            # Refund processed
            charge_id = data.get("id")
            print(f"💰 Refund processed for charge {charge_id}")
            # TODO: Update payment status

    except json.JSONDecodeError as e:
        raise WebhookVerificationError(f"Invalid JSON: {e}")

    return {"received": "true"}


@router.post(
    "/mock",
    summary="Mock Webhook (Development)",
    description="""
    Endpoint for receiving webhooks from the mock provider.

    Useful for testing without Stripe.

    Header required: `X-Webhook-Signature` with format `t=<timestamp>,v1=<signature>`
    """,
)
async def mock_webhook(
    request: Request,
    provider: Annotated[PaymentProviderPort, Depends(get_provider)],
    webhook_signature: Annotated[str, Header(alias="X-Webhook-Signature")],
) -> dict[str, Any]:
    """Handle mock webhooks for development."""
    payload = await request.body()

    # Verify signature
    if not provider.verify_webhook_signature(payload, webhook_signature):
        raise WebhookVerificationError("Invalid mock webhook signature")

    # Parse event
    try:
        event = json.loads(payload)
        event_type = event.get("type", "")
        payment_id = event.get("payment_id", "")

        print(f"📨 Mock webhook received: {event_type} for payment {payment_id}")

        # Handle event and notify n8n
        n8n_notified = False
        if event_type == "payment.succeeded":
            print(f"✅ Mock payment {payment_id} succeeded")
            # Notify n8n for orchestration
            n8n_notified = await notify_n8n(
                event_type,
                {
                    "payment_id": payment_id,
                    "status": "succeeded",
                    "provider": "mock",
                    **event.get("metadata", {}),
                },
            )
        elif event_type == "payment.failed":
            print(f"❌ Mock payment {payment_id} failed")
            n8n_notified = await notify_n8n(
                event_type,
                {
                    "payment_id": payment_id,
                    "status": "failed",
                    "provider": "mock",
                    **event.get("metadata", {}),
                },
            )

        return {
            "received": True,
            "event_type": event_type,
            "payment_id": payment_id,
            "n8n_notified": n8n_notified,
        }

    except json.JSONDecodeError as e:
        raise WebhookVerificationError(f"Invalid JSON: {e}")


@router.post(
    "/mock/confirm",
    summary="Confirm Mock Payment (Development)",
    description="""
    Simple endpoint for confirming mock payments without signature verification.

    **For development/testing only** - Do not use in production.

    This endpoint is called by the frontend mock checkout page when the user
    clicks "Pay". It triggers the payment.succeeded event and sends webhooks
    to all registered partners.
    """,
    tags=["🧪 Testing"],
)
async def confirm_mock_payment(
    request: Request,
) -> dict[str, Any]:
    """Confirm a mock payment and trigger webhooks."""
    try:
        body = await request.json()
        payment_id_str = body.get("payment_id", "")

        if not payment_id_str:
            return {"received": False, "error": "payment_id is required"}

        # Convert payment_id to UUID
        try:
            payment_id = UUID(payment_id_str)
        except ValueError:
            return {"received": False, "error": "Invalid payment_id format"}

        print(f"✅ Mock payment {payment_id} confirmed via frontend")
        print(f"   Body: {body}")

        # Get payments store
        payments_store = get_payments_store()

        # Find or create the payment
        payment = payments_store.get(payment_id)

        if not payment:
            # Create new payment if it doesn't exist
            print(f"⚠️ Payment {payment_id} not found in store, creating new one")

            # Parse currency - ensure lowercase for enum
            currency_str = body.get("currency", "USD").lower()
            try:
                currency = Currency(currency_str)
            except ValueError:
                currency = Currency.USD

            payment = Payment.create(
                amount=Decimal(str(body.get("amount", 0))),
                currency=currency,
                payment_type=PaymentType.ONE_TIME,
                provider="mock",
                reservation_id=(
                    UUID(body.get("reservation_id"))
                    if body.get("reservation_id")
                    else None
                ),
                payer_email=body.get("customer_email"),
                payer_name=body.get("customer_name"),
                description=f"Mock payment from checkout",
            )
            payment.id = payment_id  # Use the provided ID
            payments_store[payment_id] = payment
            print(f"   Created payment: {payment_id}")

        # Mark payment as succeeded
        payment.mark_succeeded()
        print(f"   Payment marked as succeeded")

        # Prepare webhook payload
        webhook_payload = {
            "payment_id": str(payment.id),
            "status": "succeeded",
            "amount": float(payment.amount),
            "currency": payment.currency.value,
            "provider": "mock",
            "reservation_id": (
                str(payment.reservation_id) if payment.reservation_id else None
            ),
            "customer_email": payment.payer_email,
            "customer_name": payment.payer_name,
            "confirmed_at": datetime.utcnow().isoformat(),
        }

        # Send webhooks to all registered partners
        print(f"📤 Sending webhooks to registered partners...")
        partner_results = await send_partner_webhooks(
            WebhookEventType.PAYMENT_SUCCEEDED, webhook_payload
        )

        print(f"   Sent {len(partner_results)} webhooks to partners")
        for result in partner_results:
            print(f"     - {result['partner_name']}: {result['status']}")

        return {
            "received": True,
            "event_type": "payment.succeeded",
            "payment_id": str(payment.id),
            "payment_status": payment.status.value,
            "webhooks_sent": len(partner_results),
            "webhook_results": partner_results,
        }

    except Exception as e:
        print(f"❌ Error confirming mock payment: {e}")
        import traceback

        traceback.print_exc()
        return {"received": False, "error": str(e)}


@router.post(
    "/partner",
    summary="Partner B2B Webhook",
    description="""
    Endpoint for receiving webhooks from B2B partners.

    - Validates HMAC signature via `X-Webhook-Signature` header
    - Format: `t=<timestamp>,v1=<signature>`

    This enables bidirectional communication between groups.
    """,
)
async def partner_webhook(
    request: Request,
    webhook_signature: Annotated[str, Header(alias="X-Webhook-Signature")],
    partner_id: Annotated[str, Header(alias="X-Partner-Id")],
) -> dict[str, Any]:
    """Handle incoming webhooks from B2B partners."""
    payload = await request.body()

    # TODO: Verify signature using partner's secret from DB
    # For now, we just log and acknowledge

    try:
        event = json.loads(payload)
        event_type = event.get("event", "")

        print(f"🤝 Partner webhook from {partner_id}: {event_type}")
        print(f"   Payload: {event}")

        # Handle different partner events
        # Example: booking.confirmed from a hotel partner
        if event_type == "booking.confirmed":
            # Create a special offer or package
            print(f"   → Processing booking confirmation from partner")

        elif event_type == "service.activated":
            # Partner activated a service for our user
            print(f"   → Processing service activation from partner")

        return {
            "received": True,
            "event_type": event_type,
            "partner_id": partner_id,
            "status": "processed",
        }

    except json.JSONDecodeError as e:
        raise WebhookVerificationError(f"Invalid JSON: {e}")


@router.post(
    "/test/generate-signature",
    summary="🧪 Generate webhook signature (Testing)",
    description="Generate a valid webhook signature for testing purposes.",
    tags=["🧪 Testing"],
)
async def generate_test_signature(
    payload: dict[str, Any],
    provider: Annotated[PaymentProviderPort, Depends(get_provider)],
) -> dict[str, str]:
    """Generate a test webhook signature."""
    if isinstance(provider, MockPaymentAdapter):
        payload_str = json.dumps(payload)
        signature = provider.generate_webhook_signature(payload_str)
        return {
            "payload": payload_str,
            "signature": signature,
            "header_name": "X-Webhook-Signature",
        }

    return {"error": "Signature generation only available for mock provider"}
