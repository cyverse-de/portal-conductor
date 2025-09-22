"""
Authentication module for Portal Conductor.

This module provides HTTP Basic Authentication support for all API endpoints.
Credentials are configured via the config file using plaintext passwords.
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from handlers import dependencies



# HTTP Basic Auth security scheme
security = HTTPBasic()


def verify_password(plain_password: str, configured_password: str) -> bool:
    """
    Verify a plain password against the configured password.

    Args:
        plain_password: The plain text password
        configured_password: The configured plain text password

    Returns:
        bool: True if password matches, False otherwise
    """
    return secrets.compare_digest(plain_password, configured_password)




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
    configured_password = auth_config.get("password")

    # Check if credentials are configured
    if not configured_username or not configured_password:
        return False

    # Check username match (constant time comparison)
    username_match = secrets.compare_digest(username, configured_username)

    # Check password match
    password_match = verify_password(password, configured_password)

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




