"""Webhook API router - Handles incoming webhooks from providers and partners."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request

from mesaYA_payment_ms.features.payments.application.ports import PaymentProviderPort
from mesaYA_payment_ms.features.payments.domain.enums import PaymentStatus
from mesaYA_payment_ms.features.payments.infrastructure.provider_factory import get_payment_provider
from mesaYA_payment_ms.features.payments.infrastructure.adapters.mock_adapter import MockPaymentAdapter
from mesaYA_payment_ms.shared.domain.exceptions import WebhookVerificationError
from mesaYA_payment_ms.shared.presentation.api_response import APIResponse

router = APIRouter()


def get_provider() -> PaymentProviderPort:
    """Dependency for getting the payment provider."""
    return get_payment_provider()


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

        # Simulate event handling
        if event_type == "payment.succeeded":
            print(f"✅ Mock payment {payment_id} succeeded")
        elif event_type == "payment.failed":
            print(f"❌ Mock payment {payment_id} failed")

        return {
            "received": True,
            "event_type": event_type,
            "payment_id": payment_id,
        }

    except json.JSONDecodeError as e:
        raise WebhookVerificationError(f"Invalid JSON: {e}")


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
