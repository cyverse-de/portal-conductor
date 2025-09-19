"""
Terrain Management API handlers.

This module contains all endpoints related to Terrain service operations
for managing user job limits and other Terrain-specific configurations.
"""

from fastapi import APIRouter, HTTPException

import kinds
from handlers import dependencies
from handlers.auth import AuthDep

router = APIRouter(prefix="/terrain", tags=["Terrain Management"])


@router.get("/users/{username}/job-limits", status_code=200, response_model=kinds.JobLimitsResponse)
def get_job_limits(username: str, current_user: AuthDep):
    """
    Retrieve current VICE job limits for a user via Terrain.

    This endpoint fetches the current concurrent job limits configured for a specific user
    in the Terrain service. Job limits control how many VICE (Visual and Interactive Computing Environment)
    jobs a user can run simultaneously, which helps manage resource allocation and system performance.

    The endpoint provides essential information for:
    - User management interfaces showing current limits
    - Administrative tools for monitoring user configurations
    - Integration systems that need to check user permissions
    - Self-service portals where users can view their current limits

    Args:
        username: The username to retrieve job limits for

    Returns:
        JobLimitsResponse: Object containing the username and current concurrent job limit

    Raises:
        HTTPException:
            - 404: If the user has no configured job limits or user doesn't exist
            - 500: If Terrain API fails due to connection, authentication, or other issues

    Example:
        GET /terrain/users/john.doe/job-limits
        Returns: {
            "username": "john.doe",
            "concurrent_jobs": 5
        }

    Note:
        - If no limits are configured for the user, returns 404
        - Requires valid Terrain admin credentials for the service account
        - Job limits may be null if no specific limit is set (inherits default)
    """
    terrain_api = dependencies.get_terrain_api()

    try:
        token = terrain_api.get_keycloak_token()
        result = terrain_api.get_concurrent_job_limits(token=token, username=username)

        # Extract concurrent_jobs from the Terrain response
        concurrent_jobs = result.get("concurrent_jobs")

        return kinds.JobLimitsResponse(
            username=username,
            concurrent_jobs=concurrent_jobs
        )
    except Exception as e:
        # Handle HTTP 404 from Terrain (user has no limits configured)
        if hasattr(e, 'response') and getattr(e.response, 'status_code', None) == 404:
            raise HTTPException(
                status_code=404,
                detail=f"No job limits configured for user '{username}'"
            )
        # Handle other errors
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve job limits: {str(e)}"
        )


@router.post("/users/{username}/job-limits", status_code=200, response_model=kinds.GenericResponse)
def set_job_limits(username: str, request: kinds.JobLimitsRequest, current_user: AuthDep):
    """
    Set VICE job limits for a user via Terrain.

    Args:
        username: Username to set limits for
        request: Job limit details

    Returns:
        GenericResponse: Success status and message

    Raises:
        HTTPException: If operation fails
    """
    terrain_api = dependencies.get_terrain_api()

    try:
        token = terrain_api.get_keycloak_token()
        terrain_api.set_concurrent_job_limits(
            token=token, username=username, limit=request.limit
        )
        return {
            "success": True,
            "message": f"Set job limit {request.limit} for user {username}",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to set job limits: {str(e)}"
        )