"""
Authentication module for Portal Conductor.

This module provides HTTP Basic Authentication support for all API endpoints.
Credentials are configured via the config file and passwords are stored as bcrypt hashes.
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext

from handlers import dependencies


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Basic Auth security scheme
security = HTTPBasic()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Args:
        plain_password: The plain text password
        hashed_password: The bcrypt hashed password

    Returns:
        bool: True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        str: Bcrypt hashed password
    """
    return pwd_context.hash(password)


def authenticate_user(username: str, password: str) -> bool:
    """
    Authenticate a user against the configured credentials.

    Args:
        username: Username to authenticate
        password: Plain text password

    Returns:
        bool: True if authentication successful, False otherwise
    """
    config = dependencies.get_config()
    auth_config = config.get("auth", {})

    # Check if authentication is disabled
    if not auth_config.get("enabled", True):
        return True

    # Get configured credentials
    configured_username = auth_config.get("username")
    configured_password_hash = auth_config.get("password")

    # Check if credentials are configured
    if not configured_username or not configured_password_hash:
        return False

    # Check username match (constant time comparison)
    username_match = secrets.compare_digest(username, configured_username)

    # Check password match
    password_match = verify_password(password, configured_password_hash)

    return username_match and password_match


def get_current_user(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> str:
    """
    Dependency function to get the current authenticated user.

    This function is used as a FastAPI dependency to protect endpoints
    that require authentication.

    Args:
        credentials: HTTP Basic Auth credentials from the request

    Returns:
        str: The authenticated username

    Raises:
        HTTPException: If authentication fails
    """
    config = dependencies.get_config()
    auth_config = config.get("auth", {})

    # Check if authentication is disabled
    if not auth_config.get("enabled", True):
        return "anonymous"

    # Authenticate the user
    if not authenticate_user(credentials.username, credentials.password):
        realm = auth_config.get("realm", "Portal Conductor API")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": f'Basic realm="{realm}"'},
        )

    return credentials.username


def get_optional_user(credentials: Annotated[HTTPBasicCredentials, Depends(security)] = None) -> str | None:
    """
    Optional dependency function for endpoints that support but don't require authentication.

    Args:
        credentials: Optional HTTP Basic Auth credentials from the request

    Returns:
        str | None: The authenticated username or None if no auth provided
    """
    if credentials is None:
        return None

    try:
        return get_current_user(credentials)
    except HTTPException:
        return None


# Type alias for the auth dependency
AuthDep = Annotated[str, Depends(get_current_user)]
OptionalAuthDep = Annotated[str | None, Depends(get_optional_user)]


def generate_password_hash(plain_password: str) -> None:
    """
    Utility function to generate a password hash for configuration.

    This is a helper function for administrators to generate bcrypt hashes
    for the configuration file.

    Args:
        plain_password: The plain text password to hash
    """
    hashed = get_password_hash(plain_password)
    print(f"Bcrypt hash for '{plain_password}': {hashed}")


if __name__ == "__main__":
    # Allow running this module directly to generate password hashes
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m handlers.auth <password>")
        print("Generates a bcrypt hash for the given password")
        sys.exit(1)

    password = sys.argv[1]
    generate_password_hash(password)