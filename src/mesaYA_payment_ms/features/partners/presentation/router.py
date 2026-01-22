"""Partners API router - B2B Integration.

Partners are managed in mesaYA_Res. This router provides read-only access
to partner information for Payment MS and testing utilities.

For partner management (create, update, delete), use the mesaYA_Res API.
"""

import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from mesaYA_payment_ms.features.partners.domain.entities import (
    WebhookEventType,
)
from mesaYA_payment_ms.features.partners.presentation.dto import (
    TestWebhookRequest,
    TestWebhookResponse,
)
from mesaYA_payment_ms.shared.presentation.api_response import APIResponse
from mesaYA_payment_ms.shared.infrastructure.http_clients import (
    get_mesa_ya_res_client,
    PartnerInfo,
)

router = APIRouter()


class PartnerReadResponse(BaseModel):
    """Partner information (read-only from mesaYA_Res)."""

    id: str
    name: str
    webhook_url: str
    subscribed_events: list[str]
    status: str
    description: str | None = None
    contact_email: str | None = None


@router.get(
    "",
    response_model=APIResponse[list[PartnerReadResponse]],
    summary="List all partners",
    description="""
    Retrieve all registered B2B partners from mesaYA_Res.

    **Note**: Partners are managed in mesaYA_Res. This endpoint fetches
    partner data for read-only purposes.
    """,
)
async def list_partners() -> APIResponse[list[PartnerReadResponse]]:
    """List all partners from mesaYA_Res."""
    client = get_mesa_ya_res_client()
    partners = await client.get_all_active_partners()

    partner_responses = [
        PartnerReadResponse(
            id=p.id,
            name=p.name,
            webhook_url=p.webhook_url,
            subscribed_events=p.subscribed_events,
            status=p.status,
            description=p.description,
            contact_email=p.contact_email,
        )
        for p in partners
    ]

    return APIResponse.ok(
        data=partner_responses,
        message=f"Found {len(partner_responses)} partners",
    )


@router.get(
    "/by-event/{event_type}",
    response_model=APIResponse[list[PartnerReadResponse]],
    summary="Get partners by subscribed event",
    description="Retrieve partners subscribed to a specific webhook event.",
)
async def get_partners_by_event(
    event_type: str,
) -> APIResponse[list[PartnerReadResponse]]:
    """Get partners subscribed to a specific event."""
    client = get_mesa_ya_res_client()
    partners = await client.get_partners_for_event(event_type)

    partner_responses = [
        PartnerReadResponse(
            id=p.id,
            name=p.name,
            webhook_url=p.webhook_url,
            subscribed_events=p.subscribed_events,
            status=p.status,
            description=p.description,
            contact_email=p.contact_email,
        )
        for p in partners
    ]

    return APIResponse.ok(
        data=partner_responses,
        message=f"Found {len(partner_responses)} partners subscribed to {event_type}",
    )


@router.post(
    "/test-webhook",
    response_model=APIResponse[TestWebhookResponse],
    summary="Test webhook delivery",
    description="""
    Send a test webhook to a specific URL.

    **For testing only** - Use this to verify your webhook endpoint
    is correctly configured and can receive webhooks.
    """,
    tags=["🧪 Testing"],
)
async def test_webhook(
    request: TestWebhookRequest,
) -> APIResponse[TestWebhookResponse]:
    """Send a test webhook to a URL."""
    # Generate a test secret if not provided
    test_secret = (
        request.secret
        or "whsec_test_"
        + hashlib.sha256(str(datetime.utcnow().timestamp()).encode()).hexdigest()[:16]
    )

    # Build test payload
    test_payload = {
        "event": request.event_type.value,
        "timestamp": datetime.utcnow().isoformat(),
        "test": True,
        "message": "This is a test webhook from MesaYA Payment MS",
        "data": {
            "payment_id": "test-payment-id",
            "amount": 100.00,
            "currency": "usd",
            "status": "succeeded",
        },
    }

    payload_json = json.dumps(test_payload)

    # Generate HMAC signature
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload_json}"
    signature = hmac.new(
        test_secret.encode(),
        signed_payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    webhook_signature = f"t={timestamp},v1={signature}"

    # Send test webhook
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                str(request.webhook_url),
                content=payload_json,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": webhook_signature,
                    "X-Partner-Id": "test-partner",
                    "X-Test-Webhook": "true",
                },
            )

            return APIResponse.ok(
                data=TestWebhookResponse(
                    success=response.status_code < 300,
                    status_code=response.status_code,
                    response_body=response.text[:500] if response.text else None,
                    signature_sent=webhook_signature,
                ),
                message=(
                    "Test webhook sent successfully"
                    if response.status_code < 300
                    else f"Webhook returned status {response.status_code}"
                ),
            )

    except httpx.TimeoutException:
        return APIResponse.ok(
            data=TestWebhookResponse(
                success=False,
                status_code=None,
                response_body=None,
                error="Request timeout",
                signature_sent=webhook_signature,
            ),
            message="Webhook request timed out",
        )
    except httpx.RequestError as e:
        return APIResponse.ok(
            data=TestWebhookResponse(
                success=False,
                status_code=None,
                response_body=None,
                error=str(e),
                signature_sent=webhook_signature,
            ),
            message=f"Webhook request failed: {e}",
        )


@router.get(
    "/info",
    summary="Partner management info",
    description="Information about managing partners.",
)
async def partner_management_info() -> dict[str, Any]:
    """Return information about partner management."""
    return {
        "message": "Partners are managed in mesaYA_Res",
        "management_endpoints": {
            "create": "POST /api/v1/partners",
            "update": "PATCH /api/v1/partners/{partnerId}",
            "delete": "DELETE /api/v1/partners/{partnerId}",
            "rotate_secret": "POST /api/v1/partners/{partnerId}/rotate-secret",
        },
        "base_url": "mesaYA_Res service (typically http://localhost:3000)",
        "documentation": "See mesaYA_Res API documentation for full partner management",
    }
