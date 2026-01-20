"""Partners API router - B2B Integration."""

import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException

from mesaYA_payment_ms.features.partners.domain.entities import (
    Partner,
    PartnerStatus,
    WebhookEventType,
)
from mesaYA_payment_ms.features.partners.presentation.dto import (
    PartnerRegisterRequest,
    PartnerUpdateRequest,
    PartnerRegisterResponse,
    PartnerResponse,
    PartnerSecretRotateResponse,
    TestWebhookRequest,
    TestWebhookResponse,
)
from mesaYA_payment_ms.shared.presentation.api_response import APIResponse
from mesaYA_payment_ms.shared.domain.exceptions import PartnerNotFoundError

router = APIRouter()

# In-memory storage for demo (replace with DB repository)
_partners_store: dict[UUID, Partner] = {}


@router.post(
    "/register",
    response_model=APIResponse[PartnerRegisterResponse],
    status_code=201,
    summary="Register a new B2B partner",
    description="""
    Register a new partner to receive webhooks.
    
    **Important**: The `secret` is only shown once. Store it securely!
    
    The secret uses HMAC-SHA256 format and should be used to validate
    the `X-Webhook-Signature` header on incoming webhooks.
    """,
)
async def register_partner(
    request: PartnerRegisterRequest,
) -> APIResponse[PartnerRegisterResponse]:
    """Register a new B2B partner."""
    partner = Partner.create(
        name=request.name,
        webhook_url=str(request.webhook_url),
        events=request.events,
        description=request.description,
        contact_email=request.contact_email,
    )

    _partners_store[partner.id] = partner

    return APIResponse.ok(
        data=PartnerRegisterResponse(
            id=partner.id,
            name=partner.name,
            webhook_url=partner.webhook_url,
            events=partner.events,
            status=partner.status,
            secret=partner.secret,
        ),
        message="Partner registered successfully. Store the secret securely!",
    )


@router.get(
    "",
    response_model=APIResponse[list[PartnerResponse]],
    summary="List all partners",
    description="Retrieve all registered B2B partners.",
)
async def list_partners() -> APIResponse[list[PartnerResponse]]:
    """List all partners."""
    partners = [
        PartnerResponse(
            id=p.id,
            name=p.name,
            webhook_url=p.webhook_url,
            events=p.events,
            status=p.status,
            description=p.description,
            contact_email=p.contact_email,
            total_webhooks_sent=p.total_webhooks_sent,
            consecutive_failures=p.consecutive_failures,
            last_webhook_at=p.last_webhook_at,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in _partners_store.values()
    ]

    return APIResponse.ok(data=partners)


@router.get(
    "/{partner_id}",
    response_model=APIResponse[PartnerResponse],
    summary="Get partner by ID",
    description="Retrieve a partner's details by ID.",
)
async def get_partner(partner_id: UUID) -> APIResponse[PartnerResponse]:
    """Get a partner by ID."""
    partner = _partners_store.get(partner_id)
    if not partner:
        raise PartnerNotFoundError(str(partner_id))

    return APIResponse.ok(
        data=PartnerResponse(
            id=partner.id,
            name=partner.name,
            webhook_url=partner.webhook_url,
            events=partner.events,
            status=partner.status,
            description=partner.description,
            contact_email=partner.contact_email,
            total_webhooks_sent=partner.total_webhooks_sent,
            consecutive_failures=partner.consecutive_failures,
            last_webhook_at=partner.last_webhook_at,
            created_at=partner.created_at,
            updated_at=partner.updated_at,
        )
    )


@router.patch(
    "/{partner_id}",
    response_model=APIResponse[PartnerResponse],
    summary="Update a partner",
    description="Update a partner's configuration.",
)
async def update_partner(
    partner_id: UUID,
    request: PartnerUpdateRequest,
) -> APIResponse[PartnerResponse]:
    """Update a partner."""
    partner = _partners_store.get(partner_id)
    if not partner:
        raise PartnerNotFoundError(str(partner_id))

    if request.name is not None:
        partner.name = request.name
    if request.webhook_url is not None:
        partner.webhook_url = str(request.webhook_url)
    if request.events is not None:
        partner.events = request.events
    if request.description is not None:
        partner.description = request.description
    if request.contact_email is not None:
        partner.contact_email = request.contact_email
    if request.status is not None:
        partner.status = request.status

    partner.updated_at = datetime.utcnow()

    return APIResponse.ok(
        data=PartnerResponse(
            id=partner.id,
            name=partner.name,
            webhook_url=partner.webhook_url,
            events=partner.events,
            status=partner.status,
            description=partner.description,
            contact_email=partner.contact_email,
            total_webhooks_sent=partner.total_webhooks_sent,
            consecutive_failures=partner.consecutive_failures,
            last_webhook_at=partner.last_webhook_at,
            created_at=partner.created_at,
            updated_at=partner.updated_at,
        ),
        message="Partner updated successfully",
    )


@router.post(
    "/{partner_id}/rotate-secret",
    response_model=APIResponse[PartnerSecretRotateResponse],
    summary="Rotate partner secret",
    description="""
    Rotate the HMAC secret for a partner.
    
    **Important**: The new secret is only shown once. The old secret
    becomes invalid immediately.
    """,
)
async def rotate_partner_secret(partner_id: UUID) -> APIResponse[PartnerSecretRotateResponse]:
    """Rotate a partner's webhook secret."""
    partner = _partners_store.get(partner_id)
    if not partner:
        raise PartnerNotFoundError(str(partner_id))

    new_secret = partner.regenerate_secret()

    return APIResponse.ok(
        data=PartnerSecretRotateResponse(
            id=partner.id,
            new_secret=new_secret,
        ),
        message="Secret rotated successfully",
    )


@router.post(
    "/{partner_id}/deactivate",
    response_model=APIResponse[PartnerResponse],
    summary="Deactivate a partner",
    description="Deactivate a partner. They will stop receiving webhooks.",
)
async def deactivate_partner(partner_id: UUID) -> APIResponse[PartnerResponse]:
    """Deactivate a partner."""
    partner = _partners_store.get(partner_id)
    if not partner:
        raise PartnerNotFoundError(str(partner_id))

    partner.deactivate()

    return APIResponse.ok(
        data=PartnerResponse(
            id=partner.id,
            name=partner.name,
            webhook_url=partner.webhook_url,
            events=partner.events,
            status=partner.status,
            description=partner.description,
            contact_email=partner.contact_email,
            total_webhooks_sent=partner.total_webhooks_sent,
            consecutive_failures=partner.consecutive_failures,
            last_webhook_at=partner.last_webhook_at,
            created_at=partner.created_at,
            updated_at=partner.updated_at,
        ),
        message="Partner deactivated",
    )


@router.post(
    "/{partner_id}/test-webhook",
    response_model=APIResponse[TestWebhookResponse],
    summary="🧪 Send test webhook to partner",
    description="""
    Send a test webhook to verify partner integration.
    
    Useful for testing the connection and signature verification.
    """,
    tags=["🧪 Testing"],
)
async def send_test_webhook(
    partner_id: UUID,
    request: TestWebhookRequest,
) -> APIResponse[TestWebhookResponse]:
    """Send a test webhook to a partner."""
    partner = _partners_store.get(partner_id)
    if not partner:
        raise PartnerNotFoundError(str(partner_id))

    # Build payload
    payload = request.payload or {
        "event": request.event_type.value,
        "timestamp": datetime.utcnow().isoformat(),
        "test": True,
        "data": {
            "message": "This is a test webhook from MesaYA Payment Service",
            "partner_id": str(partner.id),
        },
    }

    payload_json = json.dumps(payload)

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
                    "User-Agent": "MesaYA-Payment-Service/1.0",
                },
            )

            partner.record_webhook_success()

            return APIResponse.ok(
                data=TestWebhookResponse(
                    success=response.is_success,
                    message=f"Webhook sent to {partner.webhook_url}",
                    payload_sent=payload,
                    status_code=response.status_code,
                    response_body=response.text[:500] if response.text else None,
                ),
            )

    except httpx.TimeoutException:
        partner.record_webhook_failure()
        return APIResponse.ok(
            data=TestWebhookResponse(
                success=False,
                message="Webhook request timed out",
                payload_sent=payload,
            ),
        )

    except httpx.RequestError as e:
        partner.record_webhook_failure()
        return APIResponse.ok(
            data=TestWebhookResponse(
                success=False,
                message=f"Failed to send webhook: {str(e)}",
                payload_sent=payload,
            ),
        )


@router.get(
    "/events/available",
    response_model=APIResponse[list[str]],
    summary="List available webhook events",
    description="Get a list of all available webhook event types.",
)
async def list_available_events() -> APIResponse[list[str]]:
    """List all available webhook event types."""
    events = [e.value for e in WebhookEventType]
    return APIResponse.ok(data=events)
