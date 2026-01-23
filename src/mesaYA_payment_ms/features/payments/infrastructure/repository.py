"""Payment repository for database operations."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from mesaYA_payment_ms.features.payments.domain.entities import Payment
from mesaYA_payment_ms.features.payments.domain.enums import PaymentStatus
from mesaYA_payment_ms.shared.infrastructure.database.models import PaymentModel


class PaymentRepository:
    """
    Payment repository using async SQLAlchemy.

    Handles all payment persistence operations against the shared database.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, payment: Payment) -> Payment:
        """
        Create a new payment in the database.

        Args:
            payment: Payment domain entity to persist

        Returns:
            The persisted payment entity
        """
        model = PaymentModel.from_domain(payment)
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()  # Force commit immediately so other services can see it
        await self._session.refresh(model)
        print(f"💾 Payment {model.id} committed to database")
        return model.to_domain()

    async def get_by_id(self, payment_id: UUID) -> Optional[Payment]:
        """
        Get a payment by its ID.

        Args:
            payment_id: UUID of the payment

        Returns:
            Payment if found, None otherwise
        """
        result = await self._session.execute(
            select(PaymentModel).where(PaymentModel.id == payment_id)
        )
        model = result.scalar_one_or_none()
        return model.to_domain() if model else None

    async def get_by_idempotency_key(self, key: str) -> Optional[Payment]:
        """
        Get a payment by its idempotency key.

        Args:
            key: Idempotency key

        Returns:
            Payment if found, None otherwise
        """
        result = await self._session.execute(
            select(PaymentModel).where(PaymentModel.idempotency_key == key)
        )
        model = result.scalar_one_or_none()
        return model.to_domain() if model else None

    async def get_by_reservation_id(self, reservation_id: UUID) -> List[Payment]:
        """
        Get all payments for a reservation.

        Args:
            reservation_id: UUID of the reservation

        Returns:
            List of payments for the reservation
        """
        result = await self._session.execute(
            select(PaymentModel)
            .where(PaymentModel.reservation_id == reservation_id)
            .order_by(PaymentModel.created_at.desc())
        )
        models = result.scalars().all()
        return [m.to_domain() for m in models]

    async def get_by_subscription_id(self, subscription_id: UUID) -> List[Payment]:
        """
        Get all payments for a subscription.

        Args:
            subscription_id: UUID of the subscription

        Returns:
            List of payments for the subscription
        """
        result = await self._session.execute(
            select(PaymentModel)
            .where(PaymentModel.subscription_id == subscription_id)
            .order_by(PaymentModel.created_at.desc())
        )
        models = result.scalars().all()
        return [m.to_domain() for m in models]

    async def get_by_user_id(self, user_id: UUID) -> List[Payment]:
        """
        Get all payments for a user.

        Args:
            user_id: UUID of the user

        Returns:
            List of payments for the user
        """
        result = await self._session.execute(
            select(PaymentModel)
            .where(PaymentModel.user_id == user_id)
            .order_by(PaymentModel.created_at.desc())
        )
        models = result.scalars().all()
        return [m.to_domain() for m in models]

    async def update_status(
        self,
        payment_id: UUID,
        status: PaymentStatus,
        failure_reason: Optional[str] = None,
    ) -> Optional[Payment]:
        """
        Update a payment's status.

        Args:
            payment_id: UUID of the payment
            status: New payment status
            failure_reason: Optional failure reason for failed payments

        Returns:
            Updated payment if found, None otherwise
        """
        update_data = {"payment_status": status}
        if failure_reason:
            update_data["failure_reason"] = failure_reason

        await self._session.execute(
            update(PaymentModel)
            .where(PaymentModel.id == payment_id)
            .values(**update_data)
        )
        await self._session.flush()

        return await self.get_by_id(payment_id)

    async def update(self, payment: Payment) -> Optional[Payment]:
        """
        Update an existing payment with all fields.

        Args:
            payment: Payment entity with updated values

        Returns:
            Updated payment if found, None otherwise
        """
        existing = await self.get_by_id(payment.id)
        if not existing:
            return None

        await self._session.execute(
            update(PaymentModel)
            .where(PaymentModel.id == payment.id)
            .values(
                payment_status=payment.status,
                provider=payment.provider,
                provider_payment_id=payment.provider_payment_id,
                checkout_url=payment.checkout_url,
                payer_email=payment.payer_email,
                payer_name=payment.payer_name,
                description=payment.description,
                metadata=payment.metadata,
                failure_reason=payment.failure_reason,
            )
        )
        await self._session.flush()

        return await self.get_by_id(payment.id)

    async def delete(self, payment_id: UUID) -> bool:
        """
        Delete a payment.

        Args:
            payment_id: UUID of the payment to delete

        Returns:
            True if deleted, False if not found
        """
        result = await self._session.execute(
            delete(PaymentModel).where(PaymentModel.id == payment_id)
        )
        return result.rowcount > 0

    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[PaymentStatus] = None,
    ) -> List[Payment]:
        """
        List all payments with optional filtering.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            status: Optional status filter

        Returns:
            List of payments
        """
        query = select(PaymentModel).order_by(PaymentModel.created_at.desc())

        if status:
            query = query.where(PaymentModel.payment_status == status)

        query = query.limit(limit).offset(offset)

        result = await self._session.execute(query)
        models = result.scalars().all()
        return [m.to_domain() for m in models]
