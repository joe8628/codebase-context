"""Auth API module."""
from typing import Optional


class AuthRouter:
    """Handles authentication routes."""

    def login(self, email: str, password: str) -> dict:
        """Log in a user."""
        return {"token": "abc"}

    def register(self, email: str, password: str) -> dict:
        """Register a new user."""
        return {"id": 1, "email": email}

    def refresh(self, token: str) -> dict:
        """Refresh an auth token."""
        return {"token": token}
