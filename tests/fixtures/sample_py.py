"""Sample Python module for parser tests."""


class UserService:
    """Service for managing users."""

    def create(self, email: str, password: str) -> "User":
        """Create a new user."""
        return validate_email(email)

    def find_by_email(self, email: str) -> "Optional[User]":
        return None


def validate_email(email: str) -> str:
    """Validate an email address."""
    if "@" not in email:
        raise ValueError("Invalid email")
    return email


def validate_password(password: str) -> bool:
    return len(password) >= 8
