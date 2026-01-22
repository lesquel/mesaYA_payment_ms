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
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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
from mesaYA_payment_ms.features.payments.infrastructure.repository import (
    PaymentRepository,
)
from mesaYA_payment_ms.features.payments.infrastructure.adapters.mock_adapter import (
    MockPaymentAdapter,
)
from mesaYA_payment_ms.features.partners.domain.entities import (
    WebhookEventType,
)
from mesaYA_payment_ms.shared.core.settings import get_settings
from mesaYA_payment_ms.shared.domain.exceptions import WebhookVerificationError
from mesaYA_payment_ms.shared.presentation.api_response import APIResponse
from mesaYA_payment_ms.shared.infrastructure.database import get_db_session
from mesaYA_payment_ms.shared.infrastructure.http_clients import (
    get_mesa_ya_res_client,
    PartnerInfo,
)

router = APIRouter()


def get_provider() -> PaymentProviderPort:
    """Dependency for getting the payment provider."""
    return get_payment_provider()


async def get_payment_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)]
) -> PaymentRepository:
    """Dependency for getting the payment repository."""
    return PaymentRepository(session)


async def send_partner_webhooks(
    event_type: WebhookEventType, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    Send webhooks to all registered partners subscribed to the event.
    
    Fetches partners from mesaYA_Res API (partners are managed there).

    Args:
        event_type: The webhook event type
        payload: The event data payload

    Returns:
        List of webhook results with partner info and status
    """
    # Fetch partners from mesaYA_Res API
    client = get_mesa_ya_res_client()
    partners = await client.get_partners_for_event(event_type.value)
    
    if not partners:
        print(f"📭 No partners subscribed to {event_type.value}")
        return []
    
    results = []
    
    for partner in partners:
        # Skip if partner has no webhook URL
        if not partner.webhook_url:
            print(f"⏭️ Skipping partner {partner.name}: no webhook URL")
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
            async with httpx.AsyncClient(timeout=10.0) as http_client:
                response = await http_client.post(
                    partner.webhook_url,
                    content=payload_json,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": webhook_signature,
                        "X-Partner-Id": partner.id,
                    },
                )

                if response.status_code < 300:
                    print(f"✅ Webhook sent to {partner.name}: {event_type.value}")
                    results.append(
                        {
                            "partner_id": partner.id,
                            "partner_name": partner.name,
                            "status": "success",
                            "status_code": response.status_code,
                        }
                    )
                else:
                    print(
                        f"⚠️ Webhook to {partner.name} returned {response.status_code}"
                    )
                    results.append(
                        {
                            "partner_id": partner.id,
                            "partner_name": partner.name,
                            "status": "failed",
                            "status_code": response.status_code,
                            "error": response.text[:200],
                        }
                    )

        except httpx.TimeoutException:
            print(f"⏱️ Webhook timeout for {partner.name}")
            results.append(
                {
                    "partner_id": partner.id,
                    "partner_name": partner.name,
                    "status": "timeout",
                    "error": "Request timeout",
                }
            )
        except httpx.RequestError as e:
            print(f"❌ Webhook error for {partner.name}: {e}")
            results.append(
                {
                    "partner_id": partner.id,
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


# ============================================================================
# Webhook Notification Endpoint (called by mesaYA_Res gateway)
# ============================================================================

class WebhookNotifyRequest(BaseModel):
    """Request to notify partners about a payment event."""
    payment_id: str
    event_type: str  # e.g., "payment.succeeded", "payment.failed"
    metadata: dict[str, Any] | None = None


@router.post(
    "/notify",
    summary="Notify partners about payment event",
    description="""
    Endpoint called by mesaYA_Res gateway to trigger webhooks to partners.
    
    Loads the payment from database and sends webhooks to all subscribed partners.
    Also notifies n8n for orchestration workflows.
    """,
    response_model=APIResponse[dict[str, Any]],
)
async def notify_payment_event(
    request: WebhookNotifyRequest,
    repo: Annotated[PaymentRepository, Depends(get_payment_repository)],
) -> APIResponse[dict[str, Any]]:
    """Notify partners about a payment event."""
    try:
        payment_id = UUID(request.payment_id)
    except ValueError:
        return APIResponse.error(f"Invalid payment_id format: {request.payment_id}")
    
    # Load payment from database
    payment = await repo.get_by_id(payment_id)
    if not payment:
        return APIResponse.error(f"Payment not found: {request.payment_id}")
    
    print(f"📤 Notifying partners about {request.event_type} for payment {payment_id}")
    
    # Map event type string to enum
    try:
        event_type = WebhookEventType(request.event_type)
    except ValueError:
        # Default to PAYMENT_SUCCEEDED for backwards compatibility
        event_type = WebhookEventType.PAYMENT_SUCCEEDED
    
    # Prepare webhook payload
    webhook_payload = {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": float(payment.amount),
        "currency": payment.currency.value,
        "provider": payment.provider,
        "reservation_id": str(payment.reservation_id) if payment.reservation_id else None,
        "subscription_id": str(payment.subscription_id) if payment.subscription_id else None,
        "user_id": str(payment.user_id) if payment.user_id else None,
        "customer_email": payment.payer_email,
        "customer_name": payment.payer_name,
        "notified_at": datetime.utcnow().isoformat(),
        **(request.metadata or {}),
    }
    
    # Send webhooks to partners
    partner_results = await send_partner_webhooks(event_type, webhook_payload)
    
    # Notify n8n
    n8n_notified = await notify_n8n(
        request.event_type,
        {
            "payment_id": str(payment.id),
            "status": payment.status.value,
            "amount": float(payment.amount),
            "currency": payment.currency.value,
            "reservation_id": str(payment.reservation_id) if payment.reservation_id else "",
            "customer_email": payment.payer_email or "",
            "customer_name": payment.payer_name or "",
            "provider": payment.provider,
        },
    )
    
    return APIResponse.ok(
        data={
            "payment_id": str(payment.id),
            "event_type": request.event_type,
            "webhooks_sent": len(partner_results),
            "webhook_results": partner_results,
            "n8n_notified": n8n_notified,
        },
        message=f"Notified {len(partner_results)} partners",
    )


# ============================================================================
# Provider Webhook Endpoints
# ============================================================================

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
    repo: Annotated[PaymentRepository, Depends(get_payment_repository)],
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
            payment_id_str = data.get("metadata", {}).get("payment_id")
            
            if payment_id_str:
                try:
                    payment_id = UUID(payment_id_str)
                    payment = await repo.get_by_id(payment_id)
                    
                    if payment:
                        # Update status in database
                        await repo.update_status(payment_id, PaymentStatus.SUCCEEDED)
                        print(f"✅ Payment {payment_id} marked as SUCCEEDED")
                        
                        # Send webhooks to partners
                        webhook_payload = {
                            "payment_id": str(payment.id),
                            "status": "succeeded",
                            "amount": float(payment.amount),
                            "currency": payment.currency.value,
                            "provider": "stripe",
                            "session_id": session_id,
                            "reservation_id": str(payment.reservation_id) if payment.reservation_id else None,
                        }
                        await send_partner_webhooks(WebhookEventType.PAYMENT_SUCCEEDED, webhook_payload)
                        await notify_n8n("payment.succeeded", webhook_payload)
                except ValueError:
                    print(f"⚠️ Invalid payment_id in Stripe metadata: {payment_id_str}")

        elif event_type == "checkout.session.expired":
            # Payment expired/canceled
            payment_id_str = data.get("metadata", {}).get("payment_id")
            
            if payment_id_str:
                try:
                    payment_id = UUID(payment_id_str)
                    await repo.update_status(payment_id, PaymentStatus.CANCELED)
                    print(f"❌ Payment {payment_id} marked as CANCELED (expired)")
                except ValueError:
                    pass

        elif event_type == "charge.refunded":
            # Refund processed
            payment_intent_id = data.get("payment_intent")
            print(f"💰 Refund processed for payment intent {payment_intent_id}")
            # TODO: Find payment by provider_payment_id and update status

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
    repo: Annotated[PaymentRepository, Depends(get_payment_repository)],
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
        payment_id_str = event.get("payment_id", "")

        print(f"📨 Mock webhook received: {event_type} for payment {payment_id_str}")

        # Handle event and notify n8n
        n8n_notified = False
        
        if payment_id_str:
            try:
                payment_id = UUID(payment_id_str)
                payment = await repo.get_by_id(payment_id)
                
                if event_type == "payment.succeeded" and payment:
                    await repo.update_status(payment_id, PaymentStatus.SUCCEEDED)
                    print(f"✅ Mock payment {payment_id} marked as SUCCEEDED")
                    
                    n8n_notified = await notify_n8n(
                        event_type,
                        {
                            "payment_id": str(payment_id),
                            "status": "succeeded",
                            "provider": "mock",
                            **event.get("metadata", {}),
                        },
                    )
                    
                elif event_type == "payment.failed" and payment:
                    await repo.update_status(payment_id, PaymentStatus.FAILED)
                    print(f"❌ Mock payment {payment_id} marked as FAILED")
                    
                    n8n_notified = await notify_n8n(
                        event_type,
                        {
                            "payment_id": str(payment_id),
                            "status": "failed",
                            "provider": "mock",
                            **event.get("metadata", {}),
                        },
                    )
            except ValueError:
                pass

        return {
            "received": True,
            "event_type": event_type,
            "payment_id": payment_id_str,
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
    repo: Annotated[PaymentRepository, Depends(get_payment_repository)],
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

        # Get payment from database
        payment = await repo.get_by_id(payment_id)

        if not payment:
            # Create new payment if it doesn't exist
            print(f"⚠️ Payment {payment_id} not found in database, creating new one")

            # Parse currency - ensure lowercase for enum
            currency_str = body.get("currency", "USD").lower()
            try:
                currency = Currency(currency_str)
            except ValueError:
                currency = Currency.USD

            payment = Payment.create(
                amount=Decimal(str(body.get("amount", 0))),
                currency=currency,
                payment_type=PaymentType.RESERVATION,
                provider="mock",
                reservation_id=(
                    UUID(body.get("reservation_id"))
                    if body.get("reservation_id")
                    else None
                ),
                payer_email=body.get("customer_email"),
                payer_name=body.get("customer_name"),
                description="Mock payment from checkout",
            )
            # Override the generated ID with the provided one
            payment.id = payment_id
            payment = await repo.create(payment)
            print(f"   Created payment: {payment_id}")
        
        # Mark payment as succeeded in database
        payment.mark_succeeded()
        await repo.update_status(payment.id, PaymentStatus.SUCCEEDED)
        print(f"   Payment marked as succeeded in database")

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

        # Send webhooks to all registered partners (fetched from mesaYA_Res)
        print(f"📤 Sending webhooks to registered partners...")
        partner_results = await send_partner_webhooks(
            WebhookEventType.PAYMENT_SUCCEEDED, webhook_payload
        )

        print(f"   Sent {len(partner_results)} webhooks to partners")
        for result in partner_results:
            print(f"     - {result['partner_name']}: {result['status']}")

        # Notify n8n
        n8n_notified = await notify_n8n("payment.succeeded", webhook_payload)

        return {
            "received": True,
            "event_type": "payment.succeeded",
            "payment_id": str(payment.id),
            "payment_status": "succeeded",
            "webhooks_sent": len(partner_results),
            "webhook_results": partner_results,
            "n8n_notified": n8n_notified,
        }

    except Exception as e:
        print(f"❌ Error confirming mock payment: {e}")
        import traceback
        traceback.print_exc()
        return {"received": False, "error": str(e)}


# ============================================================================
# Partner Webhook Endpoints
# ============================================================================

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

    # TODO: Verify signature using partner's secret from mesaYA_Res
    # For now, we just log and acknowledge

    try:
        event = json.loads(payload)
        event_type = event.get("event", "")

        print(f"🤝 Partner webhook from {partner_id}: {event_type}")
        print(f"   Payload: {event}")

        # Handle different partner events
        if event_type == "booking.confirmed":
            print(f"   → Processing booking confirmation from partner")

        elif event_type == "service.activated":
            print(f"   → Processing service activation from partner")

        return {
            "received": True,
            "event_type": event_type,
            "partner_id": partner_id,
            "status": "processed",
        }

    except json.JSONDecodeError as e:
        raise WebhookVerificationError(f"Invalid JSON: {e}")


# ============================================================================
# Testing Endpoints
# ============================================================================

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
