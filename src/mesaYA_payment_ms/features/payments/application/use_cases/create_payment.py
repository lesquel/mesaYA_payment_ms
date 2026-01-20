"""Payment use case - Create payment."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from mesaYA_payment_ms.features.payments.application.ports import (
    PaymentProviderPort,
    PaymentIntentRequest,
)
from mesaYA_payment_ms.features.payments.domain.entities import Payment
from mesaYA_payment_ms.features.payments.domain.enums import PaymentType, Currency


@dataclass
class CreatePaymentRequest:
    """Request to create a new payment."""

    amount: Decimal
    currency: Currency = Currency.USD
    payment_type: PaymentType = PaymentType.RESERVATION

    reservation_id: UUID | None = None
    subscription_id: UUID | None = None
    user_id: UUID | None = None

    payer_email: str | None = None
    payer_name: str | None = None
    description: str | None = None
    metadata: dict | None = None

    success_url: str | None = None
    cancel_url: str | None = None
    idempotency_key: str | None = None


@dataclass
class CreatePaymentResponse:
    """Response from creating a payment."""

    payment: Payment
    checkout_url: str | None
    client_secret: str | None


class CreatePaymentUseCase:
    """
    Use case for creating a new payment.

    Orchestrates payment creation with the configured provider.
    """

    def __init__(self, provider: PaymentProviderPort) -> None:
        self._provider = provider

    async def execute(self, request: CreatePaymentRequest) -> CreatePaymentResponse:
        """
        Create a new payment.

        1. Create Payment entity in PENDING status
        2. Create payment intent with provider
        3. Update payment with provider data
        4. Return payment with checkout URL
        """
        # Create domain entity
        payment = Payment.create(
            amount=request.amount,
            currency=request.currency,
            payment_type=request.payment_type,
            provider=self._provider.provider_name,
            reservation_id=request.reservation_id,
            subscription_id=request.subscription_id,
            user_id=request.user_id,
            payer_email=request.payer_email,
            payer_name=request.payer_name,
            description=request.description,
            metadata=request.metadata,
            idempotency_key=request.idempotency_key,
        )

        # Create payment intent with provider
        intent_result = await self._provider.create_payment_intent(
            PaymentIntentRequest(
                amount=request.amount,
                currency=request.currency,
                description=request.description,
                metadata={"payment_id": str(payment.id), **(request.metadata or {})},
                success_url=request.success_url,
                cancel_url=request.cancel_url,
                payer_email=request.payer_email,
            )
        )

        # Update payment with provider data
        payment.mark_processing(
            provider_payment_id=intent_result.provider_payment_id,
            checkout_url=intent_result.checkout_url,
        )

        # TODO: Persist payment to database

        return CreatePaymentResponse(
            payment=payment,
            checkout_url=intent_result.checkout_url,
            client_secret=intent_result.client_secret,
        )
