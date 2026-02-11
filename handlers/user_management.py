"""
User Management API handlers.

This module contains all endpoints related to user management operations
including creating, updating, and deleting user accounts.
"""

import sys

import ldap
from fastapi import APIRouter, HTTPException

import kinds
import portal_ldap
from handlers import dependencies
from handlers.auth import AuthDep

router = APIRouter(prefix="/users", tags=["User Management"])
async_router = APIRouter(prefix="/async", tags=["Async Operations"])


def _ensure_formation_configured():
    """
    Ensure Formation API is configured.

    Returns:
        Formation: The configured Formation API instance.

    Raises:
        HTTPException: If Formation is not configured (503).
    """
    formation_api = dependencies.get_formation_api()
    if not formation_api:
        raise HTTPException(
            status_code=503,
            detail="Formation integration not configured."
        )
    return formation_api


def _delete_user_from_datastore(ds_api, username: str) -> None:
    """
    Delete user from datastore if they exist.

    Args:
        ds_api: DataStore API instance.
        username: Username to delete from datastore.
    """
    print(
        f"Deleting datastore files and account for user: {username}",
        file=sys.stderr
    )
    if ds_api.user_exists(username):
        ds_api.delete_home(username)
        print(
            f"Deleted home directory for user: {username}",
            file=sys.stderr
        )
        ds_api.delete_user(username)
        print(f"Deleted datastore user: {username}", file=sys.stderr)
    else:
        print(
            f"User {username} does not exist in datastore, "
            f"skipping datastore deletion",
            file=sys.stderr
        )


def _decode_group_name(group_cn) -> str:
    """
    Decode group name from LDAP result.

    Args:
        group_cn: Group CN value (bytes or str).

    Returns:
        str: Decoded group name.
    """
    return (
        group_cn.decode('utf-8')
        if isinstance(group_cn, bytes)
        else group_cn
    )


def _delete_user_from_ldap(ldap_conn, ldap_base_dn: str, username: str) -> None:
    """
    Delete user from LDAP including removing from all groups.

    Args:
        ldap_conn: LDAP connection instance.
        ldap_base_dn: LDAP base distinguished name.
        username: Username to delete from LDAP.
    """
    print(f"Checking if user {username} exists in LDAP", file=sys.stderr)
    existing_user = portal_ldap.get_user(ldap_conn, ldap_base_dn, username)

    if not existing_user or len(existing_user) == 0:
        print(
            f"User {username} does not exist in LDAP, "
            f"skipping LDAP deletion",
            file=sys.stderr
        )
        return

    # Remove from LDAP groups
    print(f"Deleting LDAP user: {username}", file=sys.stderr)
    user_groups = portal_ldap.get_user_groups(
        ldap_conn, ldap_base_dn, username
    )
    print(
        f"User {username} is in groups: {user_groups}",
        file=sys.stderr
    )

    for ug in user_groups:
        group_name = _decode_group_name(ug[1]["cn"][0])
        print(
            f"Removing user {username} from group {group_name}",
            file=sys.stderr
        )
        portal_ldap.remove_user_from_group(
            ldap_conn, ldap_base_dn, username, group_name
        )
        print(
            f"Removed user {username} from group {group_name}",
            file=sys.stderr
        )

    # Delete from LDAP
    print(f"Deleting user {username} from LDAP", file=sys.stderr)
    portal_ldap.delete_user(ldap_conn, ldap_base_dn, username)
    print(f"Deleted LDAP user: {username}", file=sys.stderr)


def _get_formation_app_username_param_id(
    formation_api, system_id: str, app_id: str
) -> str:
    """
    Get the username parameter ID from a Formation app configuration.

    Searches for the appropriate username parameter by looking for parameters
    with label "Username", or visible required Text parameters without defaults.
    The parameter IDs returned by Formation already include the step_id prefix.

    Args:
        formation_api: Formation API instance.
        system_id: Formation system ID (e.g., "de").
        app_id: Formation app UUID.

    Returns:
        str: The username parameter's ID (already qualified as "step_id_param_id").

    Raises:
        HTTPException: If username parameter cannot be determined (500).
    """
    app_params = formation_api.get_app_parameters(system_id, app_id)

    # Find the username parameter - look for parameters that match expected criteria
    if "groups" in app_params and len(app_params["groups"]) > 0:
        for group in app_params["groups"]:
            if "parameters" in group and len(group["parameters"]) > 0:
                # Strategy: Find the username parameter by looking for:
                # 1. A parameter with label containing "username" (case insensitive)
                # 2. Or a visible, required Text parameter without a defaultValue
                # 3. Or as fallback, the last visible required parameter

                parameters = group["parameters"]
                username_param = None

                # First, try to find by label
                for param in parameters:
                    label = param.get("label", "").lower()
                    if "username" in label or "user name" in label:
                        username_param = param
                        break

                # If not found by label, look for visible required text param without default
                if not username_param:
                    for param in parameters:
                        if (param.get("type") == "Text" and
                            param.get("isVisible", False) and
                            param.get("required", False) and
                            not param.get("defaultValue") and
                            not param.get("name")):  # name="" means positional arg, not flag
                            username_param = param
                            break

                # Fallback: use last visible required parameter
                if not username_param:
                    for param in reversed(parameters):
                        if param.get("isVisible", False) and param.get("required", False):
                            username_param = param
                            break

                if username_param:
                    param_id = username_param["id"]
                    return param_id

    raise HTTPException(
        status_code=500,
        detail="Could not find username parameter in app configuration. Expected a parameter with label 'Username' or a visible required Text parameter."
    )


def _resolve_formation_app_id(formation_api) -> str:
    """
    Return the Formation user-deletion app ID, retrying the lookup if it
    was not resolved at startup.

    If the cached app ID is already set, returns it immediately.  Otherwise
    attempts a by-name lookup through the Formation API and caches the
    result for subsequent calls.

    Args:
        formation_api: Configured Formation API client.

    Returns:
        str: The resolved app ID.

    Raises:
        HTTPException: 500 if the app ID cannot be resolved.
    """
    formation_app_id = dependencies.get_formation_app_id()
    if formation_app_id:
        return formation_app_id

    # Lazy retry: the startup lookup may have failed transiently
    formation_app_name = dependencies.get_formation_app_name()
    formation_system_id = dependencies.get_formation_system_id()

    if formation_app_name:
        print(
            f"[user-deletion] App ID not cached, retrying lookup "
            f"for '{formation_app_name}' in system '{formation_system_id}'",
            file=sys.stderr,
        )
        try:
            resolved_id = formation_api.get_app_id_by_name(
                formation_system_id, formation_app_name
            )
            if resolved_id:
                print(
                    f"[user-deletion] Resolved app ID: {resolved_id}",
                    file=sys.stderr,
                )
                dependencies.set_formation_app_id(resolved_id)
                return resolved_id
        except Exception as e:
            print(
                f"[user-deletion] App ID lookup failed: {e}",
                file=sys.stderr,
            )

    raise HTTPException(
        status_code=500,
        detail=(
            "Formation user deletion app ID not configured. "
            "Check that either user_deletion_app_id is set or "
            "user_deletion_app_name refers to a valid app."
        ),
    )


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

    _delete_user_from_datastore(ds_api, username)
    _delete_user_from_ldap(ldap_conn, ldap_base_dn, username)

    return {"user": username}


@async_router.delete(
    "/users/{username}",
    status_code=200,
    response_model=kinds.AsyncDeleteUserResponse,
    summary="Delete user asynchronously",
    response_description="User deletion job submitted successfully"
)
def delete_user_async(username: str, current_user: AuthDep):
    """
    Delete a user account asynchronously via Formation batch job.

    This endpoint submits an async deletion job through the Formation service,
    which runs the portal-delete-user app to perform all deletion operations.
    This is ideal for users with large home directories where synchronous
    deletion would timeout.

    ## Deletion Operations Performed

    The submitted job handles these operations in order:
    1. **Mailing Lists**: Removes user from all subscribed mailing lists
    2. **Datastore**: Deletes user's iRODS home directory and files (slow)
    3. **LDAP**: Removes user from groups and deletes LDAP account
    4. **Portal Database**: Removes user records from portal database

    ## Formation Configuration

    Configure the deletion app in `config.json`:
    ```json
    {
      "formation": {
        "user_deletion_app_id": "abc-123-def-456",  // Option 1: Direct ID
        "user_deletion_app_name": "portal-delete-user",  // Option 2: App name
        "system_id": "de"
      }
    }
    ```

    If using `user_deletion_app_name`, the app ID is automatically looked up
    at startup (not per-request for performance).

    ## Tracking Deletion Status

    Use the returned `analysis_id` with the `GET /async/status/{analysis_id}`
    endpoint to track the deletion job's progress.

    Args:
        username: The username to delete (e.g., "john.doe")

    Returns:
        AsyncDeleteUserResponse: Contains username, analysis_id for tracking,
        and initial status

    Raises:
        HTTPException:
            - 503: Formation service not configured or unavailable
            - 500: App not configured or job submission failed
            - 502: Formation API returned an error

    Example:
        ```
        DELETE /async/users/john.doe
        Response: {
          "user": "john.doe",
          "analysis_id": "abc-123-def-456",
          "status": "Submitted"
        }
        ```
    """
    import time

    formation_api = _ensure_formation_configured()
    formation_app_id = _resolve_formation_app_id(formation_api)
    formation_system_id = dependencies.get_formation_system_id()

    # Get the username parameter ID from the app configuration
    param_id = _get_formation_app_username_param_id(formation_api, formation_system_id, formation_app_id)

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
    print(f"User deletion analysis will handle: mailing lists, LDAP, iRODS, and database operations", file=sys.stderr)

    return {
        "user": username,
        "analysis_id": analysis_id,
        "status": status
    }


@async_router.get(
    "/status/{analysis_id}",
    status_code=200,
    response_model=kinds.AnalysisStatusResponse,
    summary="Get deletion job status",
    response_description="Current status of the deletion job"
)
def get_deletion_status(analysis_id: str, current_user: AuthDep):
    """
    Track the status of an async user deletion job.

    This endpoint queries the Formation service to check the current status
    of a user deletion job. Use the `analysis_id` returned from the
    `DELETE /async/users/{username}` endpoint to track job progress.

    ## Status Values

    Common status values returned by Formation:
    - **Submitted**: Job has been queued
    - **Running**: Job is currently executing
    - **Completed**: Job finished successfully
    - **Failed**: Job encountered an error

    ## Polling Recommendations

    - Poll every 5-10 seconds while status is "Submitted" or "Running"
    - Stop polling once status is "Completed" or "Failed"
    - For large home directories, jobs may run for several minutes

    Args:
        analysis_id: The UUID of the deletion job (from async delete response)

    Returns:
        AnalysisStatusResponse: Contains analysis_id, current status, and
        additional metadata from Formation

    Raises:
        HTTPException:
            - 404: Analysis ID not found in Formation
            - 503: Formation service not configured or unavailable
            - 502: Formation API returned an error

    Example:
        ```
        GET /async/status/abc-123-def-456
        Response: {
          "analysis_id": "abc-123-def-456",
          "status": "Running",
          ...
        }
        ```
    """
    formation_api = _ensure_formation_configured()

    print(f"Checking status for analysis: {analysis_id}", file=sys.stderr)
    result = formation_api.get_analysis_status(analysis_id)
    print(f"Analysis {analysis_id} status: {result.get('status')}", file=sys.stderr)
    return result


@async_router.get(
    "/analyses",
    status_code=200,
    response_model=kinds.AnalysesListResponse,
    summary="List running analyses",
    response_description="List of analyses filtered by status"
)
def list_analyses(
    status: str = "Running",
    current_user: AuthDep = None
):
    """
    List analyses filtered by status.

    This endpoint queries the Formation service to retrieve analyses
    filtered by the specified status. By default, returns only running
    analyses. Uses the Formation service account to query all analyses
    in the system.

    ## Status Values

    Common status values returned by Formation:
    - **Submitted**: Job has been queued
    - **Running**: Job is currently executing
    - **Completed**: Job finished successfully
    - **Failed**: Job encountered an error
    - **Canceled**: Job was canceled by user

    ## Polling Recommendations

    - Poll every 5-10 seconds to monitor job progress
    - Filter by status to get specific subsets of analyses

    Args:
        status: Status filter (default: "Running"). Common values:
                "Running", "Completed", "Failed", "Submitted", "Canceled"

    Returns:
        AnalysesListResponse: Contains list of analyses with their
        analysis_id, app_id, system_id, and status

    Raises:
        HTTPException:
            - 503: Formation service not configured or unavailable
            - 502: Formation API returned an error

    Example:
        ```
        GET /async/analyses?status=Running
        Response: {
          "analyses": [
            {
              "analysis_id": "abc-123-def-456",
              "app_id": "ghi-789",
              "system_id": "de",
              "status": "Running"
            }
          ]
        }
        ```
    """
    formation_api = _ensure_formation_configured()

    print(f"Listing analyses with status: {status}", file=sys.stderr)
    result = formation_api.list_analyses(status=status)
    print(f"Found {len(result.get('analyses', []))} analyses", file=sys.stderr)
    return result


@async_router.get(
    "/analyses/{analysis_id}/details",
    status_code=200,
    summary="Get analysis details including parameters",
    response_description="Full analysis details with submission parameters"
)
def get_analysis_details(
    analysis_id: str,
    current_user: AuthDep = None
):
    """
    Get detailed information about an analysis including submission parameters.

    This endpoint retrieves the full analysis details from Formation,
    including the submission configuration, parameter values, username,
    and timestamps. This is useful for viewing what parameters were
    passed to a job.

    ## Response Fields

    The response includes:
    - **id**: Analysis UUID
    - **name**: Analysis name
    - **username**: User who submitted the analysis
    - **status**: Current status
    - **submission**: Full submission configuration including:
        - **config**: Parameter values (key-value pairs)
        - **output_dir**: Output directory path
        - **notify**: Notification setting
        - **debug**: Debug mode setting
    - **start_date**: When analysis started
    - **end_date**: When analysis ended (if completed)
    - Other metadata from the apps service

    Args:
        analysis_id: The UUID of the analysis

    Returns:
        dict: Full analysis details including submission parameters

    Raises:
        HTTPException:
            - 404: Analysis ID not found
            - 503: Formation service not configured or unavailable
            - 502: Formation API returned an error

    Example:
        ```
        GET /async/analyses/abc-123-def-456/details
        Response: {
          "id": "abc-123-def-456",
          "name": "user-deletion-john.doe-1736694600",
          "username": "portal-conductor",
          "status": "Running",
          "submission": {
            "config": {
              "step1_username": "john.doe"
            },
            "output_dir": "/iplant/home/...",
            "notify": true
          },
          "start_date": "2025-01-12T14:30:00Z",
          ...
        }
        ```
    """
    formation_api = _ensure_formation_configured()

    print(f"Fetching details for analysis: {analysis_id}", file=sys.stderr)
    result = formation_api.get_analysis_details(analysis_id)
    print(f"Retrieved details for analysis: {result.get('name')}", file=sys.stderr)
    return result
