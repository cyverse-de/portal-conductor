"""
DataStore Management API handlers.

This module contains all endpoints related to datastore operations
for managing user access to datastore services.
"""

from fastapi import APIRouter, HTTPException

import kinds
from handlers import dependencies

router = APIRouter(prefix="/datastore", tags=["DataStore Management"])


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
    Register a user for datastore service access.

    Args:
        username: Username to register
        request: Service registration details

    Returns:
        GenericResponse: Success status and message

    Raises:
        HTTPException: If operation fails
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