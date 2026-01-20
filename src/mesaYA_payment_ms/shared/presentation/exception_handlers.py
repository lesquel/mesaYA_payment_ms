"""Exception handlers for the FastAPI application."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mesaYA_payment_ms.shared.domain.exceptions import (
    PaymentError,
    PaymentNotFoundError,
    PaymentProviderError,
    WebhookVerificationError,
    PartnerNotFoundError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers."""

    @app.exception_handler(PaymentNotFoundError)
    async def payment_not_found_handler(
        request: Request, exc: PaymentNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": str(exc),
                "errors": ["Payment not found"],
            },
        )

    @app.exception_handler(PartnerNotFoundError)
    async def partner_not_found_handler(
        request: Request, exc: PartnerNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": str(exc),
                "errors": ["Partner not found"],
            },
        )

    @app.exception_handler(PaymentProviderError)
    async def payment_provider_handler(
        request: Request, exc: PaymentProviderError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "message": str(exc),
                "errors": ["Payment provider error"],
            },
        )

    @app.exception_handler(WebhookVerificationError)
    async def webhook_verification_handler(
        request: Request, exc: WebhookVerificationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": str(exc),
                "errors": ["Webhook verification failed"],
            },
        )

    @app.exception_handler(PaymentError)
    async def payment_error_handler(
        request: Request, exc: PaymentError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": str(exc),
                "errors": [str(exc)],
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error",
                "errors": [str(exc)],
            },
        )
