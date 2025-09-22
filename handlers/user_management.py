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
    Delete a user account from LDAP.

    Removes the user from all groups they belong to and then deletes
    the user account from LDAP. Note: This does not delete the user's
    data store account or files.

    Args:
        username: The username to delete

    Returns:
        UserResponse: Confirmation with the deleted username

    Raises:
        HTTPException: If user deletion fails
    """
    ldap_conn = dependencies.get_ldap_conn()
    ldap_base_dn = dependencies.get_ldap_base_dn()

    print(f"Deleting LDAP user: {username}")
    user_groups = portal_ldap.get_user_groups(ldap_conn, ldap_base_dn, username)
    print(f"User {username} is in groups: {user_groups}", file=sys.stderr)
    for ug in user_groups:
        group_name = ug[1]["cn"][0]
        print(f"Removing user {username} from group {group_name}", file=sys.stderr)
        portal_ldap.remove_user_from_group(ldap_conn, ldap_base_dn, username, group_name)
        print(f"Removed user {username} from group {group_name}", file=sys.stderr)
    print(f"Deleting user {username} from LDAP", file=sys.stderr)
    portal_ldap.delete_user(ldap_conn, ldap_base_dn, username)
    print(f"Deleted LDAP user: {username}", file=sys.stderr)
    return {"user": username}
