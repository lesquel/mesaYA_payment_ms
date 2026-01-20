"""Standard API response wrapper."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper for consistent response format."""

    success: bool = True
    message: str | None = None
    data: T | None = None
    errors: list[str] | None = None

    @classmethod
    def ok(cls, data: T | None = None, message: str | None = None) -> "APIResponse[T]":
        """Create a successful response."""
        return cls(success=True, data=data, message=message)

    @classmethod
    def error(
        cls, message: str, errors: list[str] | None = None
    ) -> "APIResponse[None]":
        """Create an error response."""
        return APIResponse[None](success=False, message=message, errors=errors)

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {"id": "123"},
                "errors": None,
            }
        }
