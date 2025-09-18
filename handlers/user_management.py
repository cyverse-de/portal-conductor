"""
User Management API handlers.

This module contains all endpoints related to user management operations
including creating, updating, and deleting user accounts.
"""

import sys
import traceback

from fastapi import APIRouter, HTTPException

import kinds
import portal_datastore
import portal_ldap
from handlers import dependencies

router = APIRouter(prefix="/users", tags=["User Management"])


@router.post("/", status_code=200, response_model=kinds.UserResponse)
def add_user(user: kinds.CreateUserRequest):
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
        print(f"Creating LDAP user: {user.username}", file=sys.stderr)
        dse = portal_ldap.days_since_epoch()
        portal_ldap.create_user(ldap_conn, ldap_base_dn, dse, user)

        print(f"Setting LDAP password for: {user.username}", file=sys.stderr)
        portal_ldap.change_password(ldap_conn, ldap_base_dn, user.username, user.password)

        print(
            f"Adding user {user.username} to everyone group: {ldap_everyone_group}",
            file=sys.stderr,
        )
        portal_ldap.add_user_to_group(ldap_conn, ldap_base_dn, user.username, ldap_everyone_group)

        print(
            f"Adding user {user.username} to community group: {ldap_community_group}",
            file=sys.stderr,
        )
        portal_ldap.add_user_to_group(ldap_conn, ldap_base_dn, user.username, ldap_community_group)

        print(f"Creating data store user: {user.username}", file=sys.stderr)
        # Check if datastore service is reachable before user creation
        ds_api.health_check()
        ds_api.create_user(user.username)

        print(f"Setting data store password for: {user.username}", file=sys.stderr)
        ds_api.change_password(user.username, user.password)

        print(f"Getting home directory for: {user.username}", file=sys.stderr)
        home_dir = ds_api.user_home(user.username)

        print(f"Setting ipcservices permissions for: {home_dir}", file=sys.stderr)
        ipcservices_perm = portal_datastore.PathPermission(
            username=ipcservices_user,
            permission="own",
            path=home_dir,
        )
        ds_api.chmod(ipcservices_perm)

        print(f"Setting rodsadmin permissions for: {home_dir}", file=sys.stderr)
        rodsadmin_perm = portal_datastore.PathPermission(
            username=ds_admin_user,
            permission="own",
            path=home_dir,
        )
        ds_api.chmod(rodsadmin_perm)

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


@router.post("/{username}/password", status_code=200, response_model=kinds.UserResponse)
def change_password(username: str, request: kinds.PasswordChangeRequest):
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
def delete_user(username: str):
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