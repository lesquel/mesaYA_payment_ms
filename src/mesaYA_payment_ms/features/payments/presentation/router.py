"""Payment API router."""

import asyncio
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from mesaYA_payment_ms.features.payments.application.ports import PaymentProviderPort
from mesaYA_payment_ms.features.payments.application.use_cases import (
    CreatePaymentUseCase,
    CreatePaymentRequest as CreatePaymentUseCaseRequest,
)
from mesaYA_payment_ms.features.payments.domain.entities import Payment
from mesaYA_payment_ms.features.payments.domain.enums import PaymentStatus
from mesaYA_payment_ms.features.payments.infrastructure.provider_factory import (
    get_payment_provider,
)
from mesaYA_payment_ms.features.payments.infrastructure.repository import (
    PaymentRepository,
)
from mesaYA_payment_ms.features.payments.presentation.dto import (
    PaymentCreateRequest,
    PaymentIntentResponse,
    PaymentResponse,
    PaymentVerifyResponse,
    PaymentCancelResponse,
    PaymentRefundResponse,
)
from mesaYA_payment_ms.shared.presentation.api_response import APIResponse
from mesaYA_payment_ms.shared.domain.exceptions import PaymentNotFoundError
from mesaYA_payment_ms.shared.infrastructure.database import get_db_session
from mesaYA_payment_ms.features.partners.domain.entities import WebhookEventType
from mesaYA_payment_ms.shared.infrastructure.http_clients import get_mesa_ya_res_client

router = APIRouter()


def get_provider() -> PaymentProviderPort:
    """Dependency for getting the payment provider."""
    return get_payment_provider()


async def get_payment_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PaymentRepository:
    """Dependency for getting the payment repository."""
    return PaymentRepository(session)


async def send_payment_webhook(payment: Payment, event_type: WebhookEventType) -> None:
    """
    Send webhook notifications for a payment event.

    This is called after payment creation/update to notify partners.
    """
    from mesaYA_payment_ms.features.webhooks.presentation.router import (
        send_partner_webhooks,
    )

    print(f"🔔 Preparing to send {event_type.value} webhook for payment {payment.id}")

    # Build webhook payload
    webhook_payload = {
        "payment_id": str(payment.id),
        "amount": str(payment.amount),
        "currency": (
            payment.currency.value
            if hasattr(payment.currency, "value")
            else str(payment.currency)
        ),
        "status": (
            payment.status.value
            if hasattr(payment.status, "value")
            else str(payment.status)
        ),
        "reservation_id": (
            str(payment.reservation_id) if payment.reservation_id else None
        ),
        "user_id": str(payment.user_id) if payment.user_id else None,
        "provider": payment.provider,
        "checkout_url": payment.checkout_url,
        "description": payment.description,
        "metadata": payment.metadata,
    }

    print(f"📦 Webhook payload: {webhook_payload}")

    try:
        results = await send_partner_webhooks(event_type, webhook_payload)
        print(f"📤 Webhook results: {results}")

        if not results:
            print(f"⚠️ No webhooks sent - no partners subscribed to {event_type.value}")
    except Exception as e:
        print(f"❌ Error sending webhooks: {e}")


@router.post(
    "",
    response_model=APIResponse[PaymentIntentResponse],
    status_code=201,
    summary="Create a new payment",
    description="""
    Create a new payment/checkout session.

    - Supports idempotency via `Idempotency-Key` header
    - Returns a checkout URL for completing the payment
    - Payment starts in PENDING status until webhook confirmation
    """,
)
async def create_payment(
    request: PaymentCreateRequest,
    provider: Annotated[PaymentProviderPort, Depends(get_provider)],
    repo: Annotated[PaymentRepository, Depends(get_payment_repository)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> APIResponse[PaymentIntentResponse]:
    """Create a new payment."""
    # Check idempotency key first
    if idempotency_key:
        existing = await repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return APIResponse.ok(
                data=PaymentIntentResponse(
                    payment_id=existing.id,
                    status=existing.status,
                    provider=existing.provider,
                    checkout_url=existing.checkout_url,
                    client_secret=None,
                ),
                message="Payment already exists (idempotent)",
            )

    use_case = CreatePaymentUseCase(provider)

    result = await use_case.execute(
        CreatePaymentUseCaseRequest(
            amount=request.amount,
            currency=request.currency,
            payment_type=request.payment_type,
            reservation_id=request.reservation_id,
            subscription_id=request.subscription_id,
            user_id=request.user_id,
            payer_email=request.payer_email,
            payer_name=request.payer_name,
            description=request.description,
            metadata=request.metadata,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            idempotency_key=idempotency_key,
        )
    )

    # Persist payment to database
    persisted_payment = await repo.create(result.payment)
    print(f"✅ Payment {persisted_payment.id} persisted to database")

    # Send webhook notification for payment created (in background)
    print(f"🔔 Triggering payment.created webhook for payment {persisted_payment.id}")
    try:
        await send_payment_webhook(persisted_payment, WebhookEventType.PAYMENT_CREATED)
    except Exception as e:
        # Don't fail the request if webhook fails
        print(f"⚠️ Failed to send payment.created webhook: {e}")

    return APIResponse.ok(
        data=PaymentIntentResponse(
            payment_id=persisted_payment.id,
            status=persisted_payment.status,
            provider=persisted_payment.provider,
            checkout_url=result.checkout_url,
            client_secret=result.client_secret,
        ),
        message="Payment created successfully",
    )


@router.get(
    "/{payment_id}",
    response_model=APIResponse[PaymentResponse],
    summary="Get payment by ID",
    description="Retrieve payment details by ID.",
)
async def get_payment(
    payment_id: UUID,
    repo: Annotated[PaymentRepository, Depends(get_payment_repository)],
) -> APIResponse[PaymentResponse]:
    """Get a payment by ID."""
    payment = await repo.get_by_id(payment_id)
    if not payment:
        raise PaymentNotFoundError(str(payment_id))

    return APIResponse.ok(
        data=PaymentResponse(
            id=payment.id,
            amount=str(payment.amount),
            currency=payment.currency,
            status=payment.status,
            payment_type=payment.payment_type,
            reservation_id=payment.reservation_id,
            subscription_id=payment.subscription_id,
            user_id=payment.user_id,
            provider=payment.provider,
            provider_payment_id=payment.provider_payment_id,
            checkout_url=payment.checkout_url,
            payer_email=payment.payer_email,
            payer_name=payment.payer_name,
            description=payment.description,
            metadata=payment.metadata,
            failure_reason=payment.failure_reason,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )
    )


@router.post(
    "/{payment_id}/verify",
    response_model=APIResponse[PaymentVerifyResponse],
    summary="Verify payment status with provider",
    description="""
    Verify the current status of a payment with the provider (Stripe).

    Useful for updating status after returning from checkout.
    """,
)
async def verify_payment(
    payment_id: UUID,
    provider: Annotated[PaymentProviderPort, Depends(get_provider)],
    repo: Annotated[PaymentRepository, Depends(get_payment_repository)],
) -> APIResponse[PaymentVerifyResponse]:
    """Verify payment status with provider."""
    payment = await repo.get_by_id(payment_id)
    if not payment:
        raise PaymentNotFoundError(str(payment_id))

    previous_status = payment.status
    synchronized = False

    # Verify with provider
    if payment.provider_payment_id:
        current_status = await provider.verify_payment(payment.provider_payment_id)

        # Update payment status
        if current_status == PaymentStatus.SUCCEEDED:
            payment.mark_succeeded()
            synchronized = previous_status != payment.status
        elif current_status == PaymentStatus.FAILED:
            payment.mark_failed()
            synchronized = previous_status != payment.status
        elif current_status == PaymentStatus.CANCELED:
            payment.mark_canceled()
            synchronized = previous_status != payment.status

        # Persist status change to database
        if synchronized:
            await repo.update_status(payment.id, payment.status)
            print(f"✅ Payment {payment.id} status updated to {payment.status.value}")

    return APIResponse.ok(
        data=PaymentVerifyResponse(
            payment_id=payment.id,
            previous_status=previous_status,
            current_status=payment.status,
            synchronized=synchronized,
        ),
        message="Payment status verified" if synchronized else "Status unchanged",
    )


@router.post(
    "/{payment_id}/cancel",
    response_model=APIResponse[PaymentCancelResponse],
    summary="Cancel a pending payment",
    description="Cancel a payment that is in pending or processing status.",
)
async def cancel_payment(
    payment_id: UUID,
    provider: Annotated[PaymentProviderPort, Depends(get_provider)],
    repo: Annotated[PaymentRepository, Depends(get_payment_repository)],
) -> APIResponse[PaymentCancelResponse]:
    """Cancel a pending payment."""
    payment = await repo.get_by_id(payment_id)
    if not payment:
        raise PaymentNotFoundError(str(payment_id))

    if not payment.can_be_canceled():
        return APIResponse.ok(
            data=PaymentCancelResponse(
                payment_id=payment.id,
                status=payment.status,
                canceled=False,
            ),
            message=f"Payment cannot be canceled (status: {payment.status.value})",
        )

    # Cancel with provider
    if payment.provider_payment_id:
        await provider.cancel_payment(payment.provider_payment_id)

    payment.mark_canceled()

    # Persist to database
    await repo.update_status(payment.id, PaymentStatus.CANCELED)
    print(f"✅ Payment {payment.id} canceled")

    return APIResponse.ok(
        data=PaymentCancelResponse(
            payment_id=payment.id,
            status=payment.status,
            canceled=True,
        ),
        message="Payment canceled successfully",
    )


@router.post(
    "/{payment_id}/refund",
    response_model=APIResponse[PaymentRefundResponse],
    summary="Refund a completed payment",
    description="Perform a full refund of a completed payment.",
)
async def refund_payment(
    payment_id: UUID,
    provider: Annotated[PaymentProviderPort, Depends(get_provider)],
    repo: Annotated[PaymentRepository, Depends(get_payment_repository)],
) -> APIResponse[PaymentRefundResponse]:
    """Refund a completed payment."""
    payment = await repo.get_by_id(payment_id)
    if not payment:
        raise PaymentNotFoundError(str(payment_id))

    if not payment.can_be_refunded():
        return APIResponse.ok(
            data=PaymentRefundResponse(
                payment_id=payment.id,
                status=payment.status,
                refunded=False,
                error_message=f"Payment cannot be refunded (status: {payment.status.value})",
            ),
            message="Refund not allowed",
        )

    # Refund with provider
    if payment.provider_payment_id:
        result = await provider.refund_payment(payment.provider_payment_id)

        if result.success:
            payment.mark_refunded()
            # Persist to database
            await repo.update_status(payment.id, PaymentStatus.REFUNDED)
            print(f"✅ Payment {payment.id} refunded")

            return APIResponse.ok(
                data=PaymentRefundResponse(
                    payment_id=payment.id,
                    status=payment.status,
                    refund_id=result.refund_id,
                    refunded=True,
                ),
                message="Payment refunded successfully",
            )
        else:
            return APIResponse.ok(
                data=PaymentRefundResponse(
                    payment_id=payment.id,
                    status=payment.status,
                    refunded=False,
                    error_message=result.error_message,
                ),
                message="Refund failed",
            )

    return APIResponse.error("No provider payment ID available")


@router.get(
    "/reservation/{reservation_id}",
    response_model=APIResponse[list[PaymentResponse]],
    summary="Get payments for a reservation",
    description="Retrieve all payments associated with a reservation.",
)
async def get_reservation_payments(
    reservation_id: UUID,
    repo: Annotated[PaymentRepository, Depends(get_payment_repository)],
) -> APIResponse[list[PaymentResponse]]:
    """Get payments for a reservation."""
    payments = await repo.get_by_reservation_id(reservation_id)

    payment_responses = [
        PaymentResponse(
            id=p.id,
            amount=str(p.amount),
            currency=p.currency,
            status=p.status,
            payment_type=p.payment_type,
            reservation_id=p.reservation_id,
            subscription_id=p.subscription_id,
            user_id=p.user_id,
            provider=p.provider,
            provider_payment_id=p.provider_payment_id,
            checkout_url=p.checkout_url,
            payer_email=p.payer_email,
            payer_name=p.payer_name,
            description=p.description,
            metadata=p.metadata,
            failure_reason=p.failure_reason,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in payments
    ]

    return APIResponse.ok(data=payment_responses)
