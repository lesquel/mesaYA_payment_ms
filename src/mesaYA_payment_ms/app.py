"""FastAPI Application for Payment Microservice."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mesaYA_payment_ms.shared.core.settings import get_settings
from mesaYA_payment_ms.shared.presentation.exception_handlers import (
    register_exception_handlers,
)
from mesaYA_payment_ms.shared.infrastructure.database import init_db, close_db
from mesaYA_payment_ms.features.payments.presentation.router import (
    router as payments_router,
)
from mesaYA_payment_ms.features.webhooks.presentation.router import (
    router as webhooks_router,
)
from mesaYA_payment_ms.features.partners.presentation.router import (
    router as partners_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    # Startup
    settings = get_settings()
    print(f"🚀 Payment Microservice starting on {settings.host}:{settings.port}")
    print(f"📝 Environment: {settings.environment}")
    print(f"💳 Payment Provider: {settings.payment_provider}")

    # Initialize database connection
    await init_db()

    yield

    # Shutdown
    await close_db()
    print("👋 Payment Microservice shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="MesaYA Payment Microservice",
        description="Microservicio de pagos para MesaYA con soporte para Stripe, MercadoPago y webhooks B2B",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    # Register routers
    app.include_router(payments_router, prefix="/api/payments", tags=["Payments"])
    app.include_router(webhooks_router, prefix="/api/webhooks", tags=["Webhooks"])
    app.include_router(partners_router, prefix="/api/partners", tags=["Partners"])

    # Health endpoints
    @app.get("/", tags=["Health"])
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {"service": "MesaYA Payment Microservice", "status": "running"}

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "payment-ms",
            "provider": settings.payment_provider,
        }

    return app


app = create_app()
