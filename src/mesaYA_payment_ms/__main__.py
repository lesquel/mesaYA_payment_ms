"""Entry point for running the Payment Microservice."""

import uvicorn

from mesaYA_payment_ms.shared.core.settings import get_settings


def main() -> None:
    """Run the FastAPI application."""
    settings = get_settings()
    uvicorn.run(
        "mesaYA_payment_ms.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
