"""Payment API router."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

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

router = APIRouter()

# In-memory storage for demo (replace with DB repository)
_payments_store: dict[UUID, Payment] = {}


def get_provider() -> PaymentProviderPort:
    """Dependency for getting the payment provider."""
    return get_payment_provider()


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
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> APIResponse[PaymentIntentResponse]:
    """Create a new payment."""
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

    # Store payment (demo - use DB in production)
    _payments_store[result.payment.id] = result.payment

    return APIResponse.ok(
        data=PaymentIntentResponse(
            payment_id=result.payment.id,
            status=result.payment.status,
            provider=result.payment.provider,
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
async def get_payment(payment_id: UUID) -> APIResponse[PaymentResponse]:
    """Get a payment by ID."""
    payment = _payments_store.get(payment_id)
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
) -> APIResponse[PaymentVerifyResponse]:
    """Verify payment status with provider."""
    payment = _payments_store.get(payment_id)
    if not payment:
        raise PaymentNotFoundError(str(payment_id))

    previous_status = payment.status

    # Verify with provider
    if payment.provider_payment_id:
        current_status = await provider.verify_payment(payment.provider_payment_id)

        # Update payment status
        if current_status == PaymentStatus.SUCCEEDED:
            payment.mark_succeeded()
        elif current_status == PaymentStatus.FAILED:
            payment.mark_failed()
        elif current_status == PaymentStatus.CANCELED:
            payment.mark_canceled()

        synchronized = previous_status != payment.status
    else:
        synchronized = False

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
) -> APIResponse[PaymentCancelResponse]:
    """Cancel a pending payment."""
    payment = _payments_store.get(payment_id)
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
) -> APIResponse[PaymentRefundResponse]:
    """Refund a completed payment."""
    payment = _payments_store.get(payment_id)
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
) -> APIResponse[list[PaymentResponse]]:
    """Get payments for a reservation."""
    payments = [
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
        for p in _payments_store.values()
        if p.reservation_id == reservation_id
    ]

    return APIResponse.ok(data=payments)
