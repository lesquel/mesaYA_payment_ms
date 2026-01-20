"""Domain exceptions for the Payment Microservice."""


class PaymentError(Exception):
    """Base exception for payment errors."""

    pass


class PaymentNotFoundError(PaymentError):
    """Raised when a payment is not found."""

    def __init__(self, payment_id: str) -> None:
        self.payment_id = payment_id
        super().__init__(f"Payment with ID '{payment_id}' not found")


class PaymentProviderError(PaymentError):
    """Raised when there's an error with the payment provider."""

    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        super().__init__(f"Payment provider '{provider}' error: {message}")


class PaymentAlreadyProcessedError(PaymentError):
    """Raised when trying to process an already processed payment."""

    def __init__(self, payment_id: str, status: str) -> None:
        self.payment_id = payment_id
        self.status = status
        super().__init__(f"Payment '{payment_id}' is already in status '{status}'")


class WebhookVerificationError(PaymentError):
    """Raised when webhook signature verification fails."""

    def __init__(self, reason: str = "Invalid signature") -> None:
        super().__init__(f"Webhook verification failed: {reason}")


class PartnerNotFoundError(PaymentError):
    """Raised when a partner is not found."""

    def __init__(self, partner_id: str) -> None:
        self.partner_id = partner_id
        super().__init__(f"Partner with ID '{partner_id}' not found")


class PartnerSuspendedError(PaymentError):
    """Raised when trying to use a suspended partner."""

    def __init__(self, partner_id: str) -> None:
        self.partner_id = partner_id
        super().__init__(f"Partner '{partner_id}' is suspended")


class IdempotencyKeyConflictError(PaymentError):
    """Raised when an idempotency key has already been used."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Idempotency key '{key}' has already been used")
