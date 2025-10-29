"""
User Management API handlers.

This module contains all endpoints related to user management operations
including creating, updating, and deleting user accounts.
"""

import sys
import traceback

from fastapi import APIRouter, HTTPException
import ldap

import kinds
import portal_ldap
from handlers import dependencies
from handlers.auth import AuthDep

router = APIRouter(prefix="/users", tags=["User Management"])
async_router = APIRouter(prefix="/async", tags=["Async Operations"])


@router.post("/", status_code=200, response_model=kinds.UserResponse)
def add_user(user: kinds.CreateUserRequest, current_user: AuthDep):
    """
    Create a new user account in the CyVerse platform.

    This endpoint:
    - Creates the user in LDAP
    - Sets the user's password
    - Adds the user to default groups (everyone and community)
    - Creates the user's home directory in the data store
    - Sets appropriate permissions on the home directory

    Args:
        user: User information including personal details and credentials

    Returns:
        UserResponse: Confirmation with the created username

    Raises:
        HTTPException: If user creation fails in LDAP or data store
    """
    ldap_conn = dependencies.get_ldap_conn()
    ldap_base_dn = dependencies.get_ldap_base_dn()
    ldap_everyone_group = dependencies.get_ldap_everyone_group()
    ldap_community_group = dependencies.get_ldap_community_group()
    ds_api = dependencies.get_ds_api()
    ipcservices_user = dependencies.get_ipcservices_user()
    ds_admin_user = dependencies.get_ds_admin_user()

    try:
        # Create LDAP user with groups (idempotent)
        portal_ldap.create_ldap_user_with_groups(
            ldap_conn,
            ldap_base_dn,
            user,
            everyone_group=ldap_everyone_group,
            community_group=ldap_community_group
        )

        # Create DataStore user with permissions (mostly idempotent)
        ds_api.create_datastore_user_with_permissions(
            username=user.username,
            password=user.password,
            ipcservices_user=ipcservices_user,
            ds_admin_user=ds_admin_user
        )

        print(
            f"User creation completed successfully for: {user.username}",
            file=sys.stderr,
        )
        return {"user": user.username}

    except Exception as e:
        print(f"User creation failed for {user.username}: {str(e)}", file=sys.stderr)
        print(f"Exception type: {type(e).__name__}", file=sys.stderr)
        print(f"Traceback: {traceback.format_exc()}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"User creation failed: {str(e)}")


@router.post("/{username}/validate", status_code=200)
def validate_credentials(username: str, request: kinds.PasswordChangeRequest, current_user: AuthDep):
    """
    Validate user credentials against LDAP.

    This endpoint validates if the provided username and password combination
    is correct according to LDAP authentication.

    Args:
        username: The username to validate
        request: The password to validate

    Returns:
        dict: {"valid": True/False}

    Raises:
        HTTPException: If validation fails due to system errors
    """
    ldap_conn = dependencies.get_ldap_conn()
    ldap_base_dn = dependencies.get_ldap_base_dn()

    try:
        # Get user DN for binding
        user_dn = portal_ldap.get_user_dn(ldap_conn, ldap_base_dn, username)
        if not user_dn:
            return {"valid": False}

        # Try to bind with user credentials to validate password
        ldap_url = dependencies.get_ldap_url()
        test_conn = ldap.initialize(ldap_url)
        test_conn.simple_bind_s(user_dn, request.password)
        test_conn.unbind()

        return {"valid": True}
    except ldap.INVALID_CREDENTIALS:
        return {"valid": False}
    except Exception as e:
        print(f"LDAP validation error for {username}: {str(e)}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.post("/{username}/password", status_code=200, response_model=kinds.UserResponse)
def change_password(username: str, request: kinds.PasswordChangeRequest, current_user: AuthDep):
    """
    Change a user's password across all systems.

    Updates the password in both LDAP and the data store, and updates
    the shadow last change timestamp in LDAP.

    Args:
        username: The username whose password should be changed
        request: The new password

    Returns:
        UserResponse: Confirmation with the username

    Raises:
        HTTPException: If password change fails in LDAP or data store
    """
    ldap_conn = dependencies.get_ldap_conn()
    ldap_base_dn = dependencies.get_ldap_base_dn()
    ds_api = dependencies.get_ds_api()

    portal_ldap.change_password(ldap_conn, ldap_base_dn, username, request.password)
    dse = portal_ldap.days_since_epoch()
    portal_ldap.shadow_last_change(ldap_conn, ldap_base_dn, dse, username)
    ds_api.change_password(username, request.password)
    return {"user": username}


@router.delete("/{username}", status_code=200, response_model=kinds.UserResponse)
def delete_user(username: str, current_user: AuthDep):
    """
    Delete a user account from all systems.

    Removes the user from all groups they belong to, deletes the user account
    from LDAP, and deletes the user's datastore account and files.

    Args:
        username: The username to delete

    Returns:
        UserResponse: Confirmation with the deleted username

    Raises:
        HTTPException: If user deletion fails
    """
    ldap_conn = dependencies.get_ldap_conn()
    ldap_base_dn = dependencies.get_ldap_base_dn()
    ds_api = dependencies.get_ds_api()

    try:
        # Delete from datastore first (files and account)
        print(f"Deleting datastore files and account for user: {username}", file=sys.stderr)
        if ds_api.user_exists(username):
            ds_api.delete_home(username)
            print(f"Deleted home directory for user: {username}", file=sys.stderr)
            ds_api.delete_user(username)
            print(f"Deleted datastore user: {username}", file=sys.stderr)
        else:
            print(f"User {username} does not exist in datastore, skipping datastore deletion", file=sys.stderr)

        # Check if user exists in LDAP before attempting deletion
        print(f"Checking if user {username} exists in LDAP", file=sys.stderr)
        existing_user = portal_ldap.get_user(ldap_conn, ldap_base_dn, username)
        if existing_user and len(existing_user) > 0:
            # Remove from LDAP groups
            print(f"Deleting LDAP user: {username}", file=sys.stderr)
            user_groups = portal_ldap.get_user_groups(ldap_conn, ldap_base_dn, username)
            print(f"User {username} is in groups: {user_groups}", file=sys.stderr)
            for ug in user_groups:
                group_name = ug[1]["cn"][0].decode('utf-8') if isinstance(ug[1]["cn"][0], bytes) else ug[1]["cn"][0]
                print(f"Removing user {username} from group {group_name}", file=sys.stderr)
                portal_ldap.remove_user_from_group(ldap_conn, ldap_base_dn, username, group_name)
                print(f"Removed user {username} from group {group_name}", file=sys.stderr)

            # Delete from LDAP
            print(f"Deleting user {username} from LDAP", file=sys.stderr)
            portal_ldap.delete_user(ldap_conn, ldap_base_dn, username)
            print(f"Deleted LDAP user: {username}", file=sys.stderr)
        else:
            print(f"User {username} does not exist in LDAP, skipping LDAP deletion", file=sys.stderr)

        return {"user": username}

    except Exception as e:
        print(f"User deletion failed for {username}: {str(e)}", file=sys.stderr)
        print(f"Exception type: {type(e).__name__}", file=sys.stderr)
        print(f"Traceback: {traceback.format_exc()}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"User deletion failed: {str(e)}")


@async_router.delete("/users/{username}", status_code=200, response_model=kinds.AsyncDeleteUserResponse)
def delete_user_async(username: str, current_user: AuthDep):
    """
    Delete a user account asynchronously by submitting a deletion analysis.

    This endpoint submits a batch analysis through the formation service to handle
    long-running datastore deletion operations. It removes the user from LDAP groups
    and accounts immediately, then returns an analysis ID for tracking the datastore
    deletion progress.

    Args:
        username: The username to delete

    Returns:
        AsyncDeleteUserResponse: Confirmation with username, analysis_id, and status

    Raises:
        HTTPException: If formation API is unavailable or analysis submission fails
    """
    import time
    import httpx

    formation_api = dependencies.get_formation_api()
    formation_app_id = dependencies.get_formation_app_id()
    formation_system_id = dependencies.get_formation_system_id()
    ldap_conn = dependencies.get_ldap_conn()
    ldap_base_dn = dependencies.get_ldap_base_dn()

    # Check if formation is configured
    if not formation_api:
        raise HTTPException(
            status_code=503,
            detail="Formation integration not configured. Cannot submit async deletion."
        )

    if not formation_app_id:
        raise HTTPException(
            status_code=500,
            detail="Formation user deletion app ID not configured."
        )

    try:
        # Get app parameters to find the username parameter ID
        print(f"Getting app parameters for {formation_system_id}/{formation_app_id}", file=sys.stderr)
        app_params = formation_api.get_app_parameters(formation_system_id, formation_app_id)

        # Extract the first parameter ID (assuming single parameter for username)
        param_id = None
        if "groups" in app_params and len(app_params["groups"]) > 0:
            for group in app_params["groups"]:
                if "parameters" in group and len(group["parameters"]) > 0:
                    param_id = group["parameters"][0]["id"]
                    break

        if not param_id:
            raise HTTPException(
                status_code=500,
                detail="Could not determine parameter ID from app configuration"
            )

        # Build submission payload
        submission = {
            "name": f"user-deletion-{username}-{int(time.time())}",
            "config": {
                param_id: username
            }
        }

        # Submit the analysis
        print(f"Submitting deletion analysis for user: {username}", file=sys.stderr)
        result = formation_api.launch_analysis(
            system_id=formation_system_id,
            app_id=formation_app_id,
            submission=submission
        )

        analysis_id = result.get("analysis_id")
        status = result.get("status", "Submitted")
        print(f"Analysis submitted: {analysis_id}, status: {status}", file=sys.stderr)

        # Perform LDAP operations (fast, synchronous)
        print(f"Performing LDAP operations for user: {username}", file=sys.stderr)
        existing_user = portal_ldap.get_user(ldap_conn, ldap_base_dn, username)
        if existing_user and len(existing_user) > 0:
            # Remove from LDAP groups
            user_groups = portal_ldap.get_user_groups(ldap_conn, ldap_base_dn, username)
            print(f"User {username} is in groups: {user_groups}", file=sys.stderr)
            for ug in user_groups:
                group_name = ug[1]["cn"][0].decode('utf-8') if isinstance(ug[1]["cn"][0], bytes) else ug[1]["cn"][0]
                print(f"Removing user {username} from group {group_name}", file=sys.stderr)
                portal_ldap.remove_user_from_group(ldap_conn, ldap_base_dn, username, group_name)

            # Delete from LDAP
            print(f"Deleting user {username} from LDAP", file=sys.stderr)
            portal_ldap.delete_user(ldap_conn, ldap_base_dn, username)
            print(f"Deleted LDAP user: {username}", file=sys.stderr)
        else:
            print(f"User {username} does not exist in LDAP, skipping LDAP deletion", file=sys.stderr)

        return {
            "user": username,
            "analysis_id": analysis_id,
            "status": status
        }

    except httpx.HTTPStatusError as e:
        print(f"Formation API error: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit deletion analysis: {e.response.status_code}"
        )
    except Exception as e:
        print(f"Async user deletion failed for {username}: {str(e)}", file=sys.stderr)
        print(f"Exception type: {type(e).__name__}", file=sys.stderr)
        print(f"Traceback: {traceback.format_exc()}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Async user deletion failed: {str(e)}")


@async_router.get("/status/{analysis_id}", status_code=200, response_model=kinds.AnalysisStatusResponse)
def get_deletion_status(analysis_id: str, current_user: AuthDep):
    """
    Get the status of a user deletion analysis.

    This endpoint is a passthrough to the formation service's analysis status endpoint.
    It allows tracking the progress of async user deletion operations.

    Args:
        analysis_id: The UUID of the analysis to check

    Returns:
        AnalysisStatusResponse: Status information including analysis_id, status, and URL info

    Raises:
        HTTPException: If formation API is unavailable or analysis not found
    """
    import httpx

    formation_api = dependencies.get_formation_api()

    # Check if formation is configured
    if not formation_api:
        raise HTTPException(
            status_code=503,
            detail="Formation integration not configured."
        )

    try:
        print(f"Checking status for analysis: {analysis_id}", file=sys.stderr)
        result = formation_api.get_analysis_status(analysis_id)
        print(f"Analysis {analysis_id} status: {result.get('status')}", file=sys.stderr)
        return result

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Analysis not found: {analysis_id}"
            )
        print(f"Formation API error: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get analysis status: {e.response.status_code}"
        )
    except Exception as e:
        print(f"Failed to get deletion status for {analysis_id}: {str(e)}", file=sys.stderr)
        print(f"Exception type: {type(e).__name__}", file=sys.stderr)
        print(f"Traceback: {traceback.format_exc()}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to get deletion status: {str(e)}")
