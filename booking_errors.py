"""Compatibility import; use :mod:`app.shared.errors` in application code."""

from app.shared.errors import BookingError

__all__ = ["BookingError"]
