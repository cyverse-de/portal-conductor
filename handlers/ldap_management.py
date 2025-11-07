"""
LDAP Management API handlers.

This module contains all endpoints related to LDAP operations including
user and group management within the LDAP directory.
"""

from fastapi import APIRouter, HTTPException

import kinds
import portal_ldap
from handlers import dependencies
from handlers.auth import AuthDep

router = APIRouter(prefix="/ldap", tags=["LDAP Management"])


def _get_ldap_context():
    """
    Get common LDAP dependencies.

    Returns:
        tuple: A tuple containing (ldap_conn, ldap_base_dn).
    """
    return dependencies.get_ldap_conn(), dependencies.get_ldap_base_dn()


def _extract_group_names(groups_result):
    """
    Extract group names from LDAP group results.

    Args:
        groups_result: LDAP group query results.

    Returns:
        list[str]: List of group names.
    """
    return [g[1]["cn"][0] for g in groups_result]


@router.post("/users", status_code=200, response_model=kinds.UserResponse)
def create_ldap_user(user: kinds.CreateUserRequest, current_user: AuthDep):
    """
    Create a user in LDAP directory (idempotent).

    This endpoint creates a user account in the LDAP directory with all
    necessary attributes and optionally adds them to default groups.
    Multiple calls with the same parameters will have the same effect
    as a single call, making this operation idempotent.

    The operation performs the following steps:
    - Creates the user account in LDAP (if it doesn't exist)
    - Sets the user's password
    - Adds the user to everyone and community groups (if not already a member)

    All steps are performed idempotently - existing resources are left unchanged.

    Args:
        user: User information including personal details and credentials

    Returns:
        UserResponse: Confirmation with the created username

    Raises:
        HTTPException: If user creation or group addition fails

    Example:
        POST /ldap/users
        {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.org",
            "username": "john.doe",
            "user_uid": "12345",
            "password": "securepassword",
            "department": "IT",
            "organization": "Example University",
            "title": "Software Engineer"
        }

    Note:
        - Safe to call multiple times with the same parameters
        - Creates LDAP user with posixAccount, shadowAccount, and inetOrgPerson object classes
        - Automatically adds to configured everyone and community groups
        - Sets standard shadow password policy attributes
    """
    ldap_conn, ldap_base_dn = _get_ldap_context()
    ldap_everyone_group = dependencies.get_ldap_everyone_group()
    ldap_community_group = dependencies.get_ldap_community_group()

    portal_ldap.create_ldap_user_with_groups(
        ldap_conn,
        ldap_base_dn,
        user,
        everyone_group=ldap_everyone_group,
        community_group=ldap_community_group
    )
    return {"user": user.username}


@router.post("/users/{username}/groups/{groupname}", status_code=200, response_model=kinds.GenericResponse)
def add_user_to_ldap_group(username: str, groupname: str, current_user: AuthDep):
    """
    Add a user to an LDAP group.

    Args:
        username: Username to add to group
        groupname: LDAP group name

    Returns:
        GenericResponse: Success status and message

    Raises:
        HTTPException: If operation fails
    """
    ldap_conn, ldap_base_dn = _get_ldap_context()

    # Check if user is already in group
    user_groups = _extract_group_names(portal_ldap.get_user_groups(ldap_conn, ldap_base_dn, username))

    if groupname not in user_groups:
        portal_ldap.add_user_to_group(ldap_conn, ldap_base_dn, username, groupname)
        return {
            "success": True,
            "message": f"User {username} added to group {groupname}",
        }
    else:
        return {
            "success": True,
            "message": f"User {username} already in group {groupname}",
        }


@router.get("/users/{username}/groups", status_code=200, response_model=list[str])
def get_user_ldap_groups(username: str, current_user: AuthDep):
    """
    Get all LDAP groups for a user.

    Args:
        username: Username to lookup

    Returns:
        list[str]: List of group names the user belongs to

    Raises:
        HTTPException: If operation fails
    """
    ldap_conn, ldap_base_dn = _get_ldap_context()
    return _extract_group_names(portal_ldap.get_user_groups(ldap_conn, ldap_base_dn, username))


@router.delete("/users/{username}/groups/{groupname}", status_code=200, response_model=kinds.GenericResponse)
def remove_user_from_ldap_group(username: str, groupname: str, current_user: AuthDep):
    """
    Remove a user from an LDAP group.

    Args:
        username: Username to remove from group
        groupname: LDAP group name

    Returns:
        GenericResponse: Success status and message

    Raises:
        HTTPException: If operation fails
    """
    ldap_conn, ldap_base_dn = _get_ldap_context()

    portal_ldap.remove_user_from_group(ldap_conn, ldap_base_dn, username, groupname)
    return {
        "success": True,
        "message": f"User {username} removed from group {groupname}",
    }


@router.get("/users/{username}", status_code=200, response_model=kinds.UserLDAPInfo)
def get_user_ldap_info(username: str, current_user: AuthDep):
    """
    Retrieve comprehensive LDAP information for a user.

    This endpoint returns detailed user information from the LDAP directory,
    including personal details, system attributes, and shadow account settings.
    It provides a complete view of a user's LDAP profile for administrative
    and integration purposes.

    The returned information includes:
    - Basic user identifiers (UID, GID numbers)
    - Personal information (name, email, department, organization, title)
    - System settings (home directory, login shell)
    - Shadow account password policy settings
    - LDAP object classes

    Args:
        username: The username to retrieve LDAP information for

    Returns:
        UserLDAPInfo: Complete LDAP user information including all available attributes

    Raises:
        HTTPException:
            - 404: If the user is not found in LDAP
            - 500: If LDAP query fails due to connection or other issues

    Example:
        GET /ldap/users/john.doe
        Returns: {
            "username": "john.doe",
            "uid_number": 12345,
            "gid_number": 10013,
            "given_name": "John",
            "surname": "Doe",
            "common_name": "John Doe",
            "email": "john.doe@example.org",
            "department": "IT",
            "organization": "Example University",
            "title": "Software Engineer",
            "home_directory": "/home/john.doe",
            "login_shell": "/bin/bash",
            "shadow_last_change": 19234,
            "shadow_min": 1,
            "shadow_max": 730,
            "shadow_warning": 10,
            "shadow_inactive": 10,
            "object_classes": ["posixAccount", "shadowAccount", "inetOrgPerson"]
        }
    """
    ldap_conn, ldap_base_dn = _get_ldap_context()

    user_result = portal_ldap.get_user(ldap_conn, ldap_base_dn, username)

    if not user_result or len(user_result) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"User '{username}' not found in LDAP directory"
        )

    user_attrs = portal_ldap.parse_user_attributes(user_result)
    if user_attrs is None:
        raise HTTPException(
            status_code=404,
            detail=f"Failed to parse LDAP attributes for user '{username}'"
        )

    return kinds.UserLDAPInfo(
        username=username,
        uid_number=user_attrs.get("uid_number"),
        gid_number=user_attrs.get("gid_number"),
        given_name=user_attrs.get("given_name"),
        surname=user_attrs.get("surname"),
        common_name=user_attrs.get("common_name"),
        email=user_attrs.get("email"),
        department=user_attrs.get("department"),
        organization=user_attrs.get("organization"),
        title=user_attrs.get("title"),
        home_directory=user_attrs.get("home_directory"),
        login_shell=user_attrs.get("login_shell"),
        shadow_last_change=user_attrs.get("shadow_last_change"),
        shadow_min=user_attrs.get("shadow_min"),
        shadow_max=user_attrs.get("shadow_max"),
        shadow_warning=user_attrs.get("shadow_warning"),
        shadow_inactive=user_attrs.get("shadow_inactive"),
        object_classes=user_attrs.get("object_classes")
    )


@router.get("/groups", status_code=200, response_model=list[kinds.LDAPGroupInfo])
def get_ldap_groups(current_user: AuthDep):
    """
    Retrieve all available LDAP groups that users can join.

    This endpoint returns a comprehensive list of all LDAP groups (posixGroup objects)
    available in the directory. It provides essential group information for user
    management interfaces, administrative tools, and integration systems that need
    to display or manage group memberships.

    The returned information for each group includes:
    - Group name (cn) - the primary identifier for the group
    - Group ID number (gidNumber) - numeric group identifier
    - Display name - human-readable group name if available
    - Description - group purpose or description
    - Samba-related attributes (group type and SID) if configured
    - LDAP object classes

    This endpoint is particularly useful for:
    - Populating group selection interfaces in user management UIs
    - Administrative tools that need to display available groups
    - Integration systems that synchronize group information
    - Reporting and auditing tools

    Returns:
        list[LDAPGroupInfo]: List of all available LDAP groups with their details

    Raises:
        HTTPException: If LDAP query fails due to connection or other issues

    Example:
        GET /ldap/groups
        Returns: [
            {
                "name": "developers",
                "gid_number": 10001,
                "display_name": "Development Team",
                "description": "Software development group",
                "samba_group_type": 2,
                "samba_sid": "S-1-5-21-...",
                "object_classes": ["posixGroup", "sambaGroupMapping"]
            },
            {
                "name": "community",
                "gid_number": 10013,
                "display_name": "Community Users",
                "description": "General community group for all users",
                "samba_group_type": null,
                "samba_sid": null,
                "object_classes": ["posixGroup"]
            }
        ]
    """
    ldap_conn, ldap_base_dn = _get_ldap_context()

    groups_result = portal_ldap.get_groups(ldap_conn, ldap_base_dn)

    if not groups_result:
        return []

    groups_list = []
    for group_result in groups_result:
        group_attrs = portal_ldap.parse_group_attributes(group_result)
        if group_attrs and group_attrs.get("name"):
            groups_list.append(kinds.LDAPGroupInfo(
                name=group_attrs["name"],
                gid_number=group_attrs.get("gid_number"),
                display_name=group_attrs.get("display_name"),
                description=group_attrs.get("description"),
                samba_group_type=group_attrs.get("samba_group_type"),
                samba_sid=group_attrs.get("samba_sid"),
                object_classes=group_attrs.get("object_classes")
            ))

    # Sort groups by name for consistent ordering
    groups_list.sort(key=lambda g: g.name.lower())
    return groups_list


@router.get("/users/{username}/exists", status_code=200, response_model=kinds.UserExistsResponse)
def check_user_exists_in_ldap(username: str, current_user: AuthDep):
    """
    Check if a user exists in LDAP directory.

    This endpoint verifies whether a given username exists as a posixAccount
    in the LDAP directory. It's useful for validation before attempting user
    operations or for user existence checks in external systems.

    Args:
        username: The username to check for existence in LDAP

    Returns:
        UserExistsResponse: Object containing the username and existence status

    Raises:
        HTTPException: If LDAP query fails due to connection or other issues

    Example:
        GET /ldap/users/john.doe/exists
        Returns: {"username": "john.doe", "exists": true}
    """
    ldap_conn, ldap_base_dn = _get_ldap_context()

    user_result = portal_ldap.get_user(ldap_conn, ldap_base_dn, username)
    exists = bool(user_result and len(user_result) > 0)
    return kinds.UserExistsResponse(username=username, exists=exists)


@router.put("/users/{username}/attributes/{attribute}", status_code=200, response_model=kinds.GenericResponse)
def modify_user_ldap_attribute(username: str, attribute: str, request: kinds.UserAttributeModifyRequest, current_user: AuthDep):
    """
    Modify a user's LDAP attribute.

    This endpoint allows updating specific LDAP attributes for a user, such as
    email address, first name, last name, or common name. It provides a generic
    interface for LDAP attribute modifications while maintaining proper validation
    and error handling.

    Common attributes that can be modified:
    - mail: Email address
    - givenName: First name
    - sn: Surname/last name
    - cn: Common name (full name)
    - title: Job title
    - telephoneNumber: Phone number

    Args:
        username: The username whose attribute should be modified
        attribute: The LDAP attribute name to modify
        request: Request body containing the new value

    Returns:
        GenericResponse: Success status and message

    Raises:
        HTTPException: If user doesn't exist, attribute modification fails, or validation errors

    Example:
        PUT /ldap/users/john.doe/attributes/mail
        {"value": "john.doe@newdomain.com"}

        Returns: {"success": true, "message": "Updated attribute 'mail' for user 'john.doe'"}
    """
    ldap_conn, ldap_base_dn = _get_ldap_context()

    # First check if user exists
    user_result = portal_ldap.get_user(ldap_conn, ldap_base_dn, username)
    if not user_result or len(user_result) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"User '{username}' not found in LDAP directory"
        )

    # Modify the attribute
    try:
        portal_ldap.modify_user_attribute(ldap_conn, ldap_base_dn, username, attribute, request.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return kinds.GenericResponse(
        success=True,
        message=f"Updated attribute '{attribute}' for user '{username}'"
    )