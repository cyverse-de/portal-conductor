"""
Portal Database Management API handlers.

This module contains endpoints for portal database operations including
checking user/email existence and creating users across all systems.
"""

import sys

from fastapi import APIRouter, HTTPException

import kinds
import portal_ldap
from handlers import dependencies
from handlers.auth import AuthDep
from handlers.validators import username_valid

router = APIRouter(prefix="/portal", tags=["Portal Database"])


def _ensure_portal_db_configured():
    """
    Ensure portal database is configured.

    Returns:
        PortalDB: The configured portal database instance.

    Raises:
        HTTPException: If portal database is not configured (503).
    """
    portal_db = dependencies.get_portal_db()
    if not portal_db:
        raise HTTPException(
            status_code=503,
            detail="Portal database not configured."
        )
    return portal_db


@router.get(
    "/users/{username}/exists",
    status_code=200,
    response_model=kinds.PortalUserExistsResponse,
    summary="Check if username exists",
)
def check_username_exists(username: str, current_user: AuthDep):
    """
    Check if a username exists in the portal database.

    Checks both the account_user table and account_restrictedusername table.

    Args:
        username: Username to check.

    Returns:
        PortalUserExistsResponse with exists=True if the username is taken
        or restricted.
    """
    portal_db = _ensure_portal_db_configured()

    is_valid = username_valid(username)
    user_exists = portal_db.user_exists_by_username(username)
    is_restricted = portal_db.is_restricted_username(username)

    return kinds.PortalUserExistsResponse(
        username=username,
        valid=is_valid,
        exists=user_exists or is_restricted,
        is_restricted=is_restricted,
    )


@router.get(
    "/emails/{email}/exists",
    status_code=200,
    response_model=kinds.PortalEmailExistsResponse,
    summary="Check if email exists",
)
def check_email_exists(email: str, current_user: AuthDep):
    """
    Check if an email address exists in the portal database.

    Performs a case-insensitive check against the account_emailaddress table.

    Args:
        email: Email address to check.

    Returns:
        PortalEmailExistsResponse with exists=True if the email is in use.
    """
    portal_db = _ensure_portal_db_configured()

    exists = portal_db.email_exists(email)

    return kinds.PortalEmailExistsResponse(
        email=email,
        exists=exists,
    )


@router.post(
    "/users/{username}/validate",
    status_code=200,
    response_model=kinds.UsernameValidationResponse,
    summary="Validate username",
)
def validate_username(username: str, current_user: AuthDep):
    """
    Validate a username against requirements.

    Checks:
    - Username is not in the restricted usernames list.
    - Username is not already taken by another user.

    Args:
        username: Username to validate.

    Returns:
        UsernameValidationResponse with valid=True if username can be used.
    """
    portal_db = _ensure_portal_db_configured()

    # Check if the username format is valid.
    if not username_valid(username):
        return kinds.UsernameValidationResponse(
            username=username,
            valid=False,
            reason="Username format is invalid.",
        )

    # Check if username is restricted
    if portal_db.is_restricted_username(username):
        return kinds.UsernameValidationResponse(
            username=username,
            valid=False,
            reason="Username is restricted.",
        )

    # Check if username already exists
    if portal_db.user_exists_by_username(username):
        return kinds.UsernameValidationResponse(
            username=username,
            valid=False,
            reason="Username already taken.",
        )

    return kinds.UsernameValidationResponse(
        username=username,
        valid=True,
        reason=None,
    )


@router.post(
    "/users",
    status_code=201,
    response_model=kinds.CreatePortalUserResponse,
    summary="Create user in all systems",
)
def create_portal_user(
    request: kinds.CreatePortalUserRequest,
    current_user: AuthDep,
):
    """
    Create a user in all systems: Portal DB, LDAP, DataStore, and Terrain.

    This endpoint performs a complete user registration:
    1. Creates the user record in the portal database.
    2. Creates the email address record in the portal database.
    3. Creates the user in LDAP with default group memberships.
    4. Creates the user in the DataStore (iRODS) with home directory.
    5. Sets job limits via Terrain (if configured).

    Args:
        request: User creation request with all required fields.

    Returns:
        CreatePortalUserResponse with username and database user ID.

    Raises:
        HTTPException: 400 if username/email already exists.
        HTTPException: 503 if required services are not configured.
    """
    portal_db = _ensure_portal_db_configured()
    ldap_conn = dependencies.get_ldap_conn()
    ldap_base_dn = dependencies.get_ldap_base_dn()
    ldap_everyone_group = dependencies.get_ldap_everyone_group()
    ldap_community_group = dependencies.get_ldap_community_group()
    ds_api = dependencies.get_ds_api()
    ipcservices_user = dependencies.get_ipcservices_user()
    ds_admin_user = dependencies.get_ds_admin_user()
    terrain_api = dependencies.get_terrain_api()

    # Validate username
    if portal_db.is_restricted_username(request.username):
        raise HTTPException(
            status_code=400,
            detail="Username is restricted.",
        )

    if portal_db.user_exists_by_username(request.username):
        raise HTTPException(
            status_code=400,
            detail="Username already taken.",
        )

    # Validate email
    if portal_db.email_exists(request.email):
        raise HTTPException(
            status_code=400,
            detail="Email already in use.",
        )

    # Get occupation name for LDAP title field
    occupation_name = portal_db.get_occupation_name(request.occupation_id)
    if not occupation_name:
        occupation_name = "Unknown"

    # 1. Create user in portal database
    print(f"Creating user in portal database: {request.username}", file=sys.stderr)
    user_data = {
        "username": request.username,
        "email": request.email,
        "password": "",  # Password will be set separately via email confirmation
        "first_name": request.first_name,
        "last_name": request.last_name,
        "institution": request.institution,
        "department": request.department,
        "occupation_id": request.occupation_id,
        "funding_agency_id": request.funding_agency_id,
        "gender_id": request.gender_id,
        "ethnicity_id": request.ethnicity_id,
        "region_id": request.region_id,
        "research_area_id": request.research_area_id,
        "aware_channel_id": request.aware_channel_id,
        "grid_institution_id": request.grid_institution_id,
    }
    user_id = portal_db.create_user(user_data)

    # 2. Create email address record
    print(f"Creating email address record for user {user_id}", file=sys.stderr)
    portal_db.create_email_address(
        user_id=user_id,
        email=request.email,
        primary=True,
        verified=False,
    )

    # 3. Create user in LDAP with groups
    # Calculate uidNumber: user_id + offset (matching portal2 behavior)
    config = dependencies.get_config()
    security_config = config.get("security", {}) if config else {}
    uid_number_offset = security_config.get("uidNumberOffset", 2831)
    user_uid = str(user_id + uid_number_offset)

    print(f"Creating LDAP user: {request.username} (uid: {user_uid})", file=sys.stderr)
    ldap_user = kinds.CreateUserRequest(
        first_name=request.first_name,
        last_name=request.last_name,
        email=request.email,
        username=request.username,
        user_uid=user_uid,
        password=request.password,
        department=request.department,
        organization=request.institution,
        title=occupation_name,
    )
    portal_ldap.create_ldap_user_with_groups(
        ldap_conn,
        ldap_base_dn,
        ldap_user,
        everyone_group=ldap_everyone_group,
        community_group=ldap_community_group,
    )

    # 4. Create user in DataStore
    print(f"Creating DataStore user: {request.username}", file=sys.stderr)
    ds_api.create_datastore_user_with_permissions(
        username=request.username,
        password=request.password,
        ipcservices_user=ipcservices_user,
        ds_admin_user=ds_admin_user,
    )

    # 5. Set job limits via Terrain (optional)
    if terrain_api and request.job_limit is not None:
        print(f"Setting job limits for user: {request.username}", file=sys.stderr)
        try:
            terrain_api.set_concurrent_job_limits(
                request.username,
                request.job_limit,
            )
        except Exception as e:
            print(
                f"WARNING: Failed to set job limits for {request.username}: {e}",
                file=sys.stderr,
            )
            # Continue - job limits are not critical

    print(f"User creation completed: {request.username} (id={user_id})", file=sys.stderr)
    return kinds.CreatePortalUserResponse(
        user=request.username,
        user_id=user_id,
    )
