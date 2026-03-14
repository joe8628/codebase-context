"""Validation utilities."""


def validate_email(email: str) -> str:
    """Validate an email address."""
    if "@" not in email:
        raise ValueError("Invalid email")
    return email.lower()


def validate_password(password: str) -> bool:
    """Validate password strength."""
    return len(password) >= 8
