"""Imports every model module, so Base.metadata lists all tables (used by Alembic)."""

from pushtalk.auth.models import RefreshToken, User

__all__ = ["RefreshToken", "User"]
