"""
DataStore Management API handlers.

This module contains all endpoints related to datastore operations
for managing user access to datastore services.
"""

from fastapi import APIRouter, HTTPException

import kinds
from handlers import dependencies

router = APIRouter(prefix="/datastore", tags=["DataStore Management"])


@router.post("/users", status_code=200, response_model=kinds.UserResponse)
def create_datastore_user(request: kinds.DatastoreUserRequest):
    """
    Create a user in the iRODS datastore or reset an existing user's password.

    This endpoint creates a user account in the iRODS datastore with all
    necessary permissions and home directory setup. Most operations are
    idempotent, with the exception of password setting which is always
    performed for security reasons.

    **Password Reset Usage**: This endpoint can be used to reset passwords for
    existing users by providing their username and new password. The password
    will be updated regardless of whether the user already exists.

    The operation performs the following steps:
    - Creates the user account in iRODS (if it doesn't exist)
    - Creates the user's home directory (if it doesn't exist)
    - Sets the user's password (always updated - enables password reset)
    - Sets ownership permissions for ipcservices and admin users (if not set)

    All steps except password setting are performed idempotently - existing
    resources are left unchanged.

    Args:
        request: DataStore user creation details including username and password

    Returns:
        UserResponse: Confirmation with the created/updated username

    Raises:
        HTTPException: If user creation, directory creation, or permission setting fails

    Examples:
        # Create new user
        POST /datastore/users
        {
            "username": "new.user",
            "password": "securepassword"
        }

        # Reset existing user's password
        POST /datastore/users
        {
            "username": "existing.user",
            "password": "new_secure_password"
        }

    Note:
        - Safe to call multiple times (password will be reset each time)
        - Can be used for both user creation and password reset
        - Creates iRODS user with rodsuser type
        - Sets up home directory with proper ownership
        - Grants ownership to configured ipcservices and admin users
        - Password setting is not idempotent by design for security reasons
    """
    ds_api = dependencies.get_ds_api()
    ipcservices_user = dependencies.get_ipcservices_user()
    ds_admin_user = dependencies.get_ds_admin_user()

    try:
        ds_api.create_datastore_user_with_permissions(
            username=request.username,
            password=request.password,
            ipcservices_user=ipcservices_user,
            ds_admin_user=ds_admin_user
        )
        return {"user": request.username}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create datastore user: {str(e)}"
        )


@router.get("/users/{username}/exists", status_code=200, response_model=kinds.UserExistsResponse)
def check_user_exists_in_datastore(username: str):
    """
    Check if a user exists in the iRODS data store.

    This endpoint verifies whether a given username exists as a user account
    in the iRODS data store system. It provides essential validation for data store
    operations and user account management workflows.

    The endpoint is particularly useful for:
    - Pre-validation before attempting iRODS data store operations
    - User account verification for external integrations and services
    - Administrative user management interfaces and dashboards
    - Service registration validation to ensure users exist before setup
    - Integration systems that need to verify data store access permissions
    - Auditing and reporting tools for user account management

    This check operates at the iRODS user level and validates whether the user
    account exists within the configured iRODS zone. It does not check for
    specific permissions or data access rights, only account existence.

    Args:
        username: The username to check for existence in the iRODS data store

    Returns:
        UserExistsResponse: Object containing the username and existence status

    Raises:
        HTTPException: If data store query fails due to connection, authentication,
                      or other iRODS system issues

    Example:
        GET /datastore/users/john.doe/exists
        Returns: {
            "username": "john.doe",
            "exists": true
        }

    Note:
        - Uses the configured iRODS zone for user lookups
        - Requires valid iRODS admin credentials for the service account
        - Returns false for users that exist in other zones but not the configured zone
        - Network or authentication failures will result in 500 errors, not false
    """
    ds_api = dependencies.get_ds_api()

    try:
        exists = ds_api.user_exists(username)
        return kinds.UserExistsResponse(username=username, exists=exists)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check user existence in data store: {str(e)}"
        )


@router.post("/users/{username}/services", status_code=200, response_model=kinds.GenericResponse)
def register_datastore_service(username: str, request: kinds.DatastoreServiceRequest):
    """
    Register a user for datastore service access (idempotent).

    This endpoint creates or ensures existence of a datastore service registration
    for a user. Multiple calls with the same parameters will have the same effect
    as a single call, making this operation idempotent.

    The operation performs the following steps:
    - Creates the user account in iRODS if it doesn't exist
    - Creates the user's home directory if needed
    - Creates the specified service directory under the user's home path
    - Sets appropriate permissions (inherit, owner for user, and optionally for irods_user)

    All steps are performed idempotently - existing resources are left unchanged.

    Args:
        username: Username to register for datastore service
        request: Service registration details including irods_path and optional irods_user

    Returns:
        GenericResponse: Success status and confirmation message

    Raises:
        HTTPException: If user creation, directory creation, or permission setting fails

    Example:
        POST /datastore/users/john.doe/services
        {
            "irods_path": "my-service-data",
            "irods_user": "service-account"
        }

    Note:
        - Safe to call multiple times with the same parameters
        - Creates full directory path: /{zone}/home/{username}/{irods_path}
        - Sets inherit permission on the directory
        - Grants ownership to both username and irods_user (if specified)
    """
    ds_api = dependencies.get_ds_api()

    try:
        ds_api.register_service(
            username=username,
            irods_path=request.irods_path,
            irods_user=request.irods_user,
        )
        return {
            "success": True,
            "message": f"User {username} registered for datastore service {request.irods_path}",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to register datastore service: {str(e)}"
        )