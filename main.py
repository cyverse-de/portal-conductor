import os
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

import email_service
import mailman
import portal_datastore
import portal_ldap
import terrain

app = FastAPI(
    title="Portal Conductor API",
    description="API for managing user accounts, email lists, and service registrations in the CyVerse platform",
    version="1.0.0",
    contact={
        "name": "CyVerse Support",
        "url": "https://cyverse.org",
    },
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    print(exc, file=sys.stderr)
    return JSONResponse(content={"detail": exc.detail}, status_code=exc.status_code)


@app.middleware("http")
async def exception_handling_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return JSONResponse(content=str(e), status_code=500)


portal_ldap_url = os.environ.get("PORTAL_LDAP_URL") or "http://portal-ldap/"
portal_datastore_url = (
    os.environ.get("PORTAL_DATASTORE_URL") or "http://portal-datastore/"
)
ldap_community_group = os.environ.get("LDAP_COMMUNITY_GROUP") or "community"
ipcservices_user = os.environ.get("IPCSERVICES_USER") or "ipcservices"
ds_admin_user = os.environ.get("DS_ADMIN_USER") or "rodsadmin"
terrain_url = os.environ.get("TERRAIN_URL") or "http://terrain/"

terrain_user = os.environ.get("TERRAIN_USER") or ""
if terrain_user == "":
    print("TERRAIN_USER must be set", file=sys.stderr)
    sys.exit(1)

terrain_password = os.environ.get("TERRAIN_PASSWORD") or ""
if terrain_password == "":
    print("TERRAIN_PASSWORD must be set", file=sys.stderr)
    sys.exit(1)

ldap_everyone_group = os.environ.get("LDAP_EVERYONE_GROUP") or ""
if ldap_everyone_group == "":
    print("LDAP_EVERYONE_GROUP must be set", file=sys.stderr)
    sys.exit(1)

mailman_enabled = os.environ.get("MAILMAN_ENABLED") or "false"
mailman_enabled = mailman_enabled.lower() in ["1", "true", "yes"]
if not mailman_enabled:
    print("MAILMAN_ENABLED is not set to true, mailman integration disabled")

mailmain_url = os.environ.get("MAILMAN_URL") or ""
if mailmain_url == "":
    print("MAILMAN_URL must be set", file=sys.stderr)
    sys.exit(1)

mailman_password = os.environ.get("MAILMAN_PASSWORD") or ""
if mailman_password == "":
    print("MAILMAN_PASSWORD must be set", file=sys.stderr)
    sys.exit(1)


ldap_api = portal_ldap.LDAP(portal_ldap_url)
ds_api = portal_datastore.DataStore(portal_datastore_url)
terrain_api = terrain.Terrain(
    api_url=terrain_url, username=terrain_user, password=terrain_password
)
email_api = mailman.Mailman(api_url=mailmain_url, password=mailman_password)
smtp_service = email_service.EmailService()


class PasswordChangeRequest(BaseModel):
    password: str


class UserResponse(BaseModel):
    user: str


class EmailListResponse(BaseModel):
    list: str
    email: str


class ServiceKeysResponse(BaseModel):
    approval_keys: list[str]


class ServiceRegistrationUser(BaseModel):
    username: str
    email: str


class ServiceRegistrationService(BaseModel):
    approval_key: str


class ServiceRegistrationRequest(BaseModel):
    user: ServiceRegistrationUser
    service: ServiceRegistrationService


class ServiceRegistrationResponse(BaseModel):
    user: str
    service: str
    ldap_group: str | None = None
    irods_path: str | None = None
    irods_user: str | None = None
    mailing_list: list[str] | None = None
    custom_action: str | None = None


class EmailRequest(BaseModel):
    to: str | list[str]
    subject: str
    text_body: str | None = None
    html_body: str | None = None
    from_email: str | None = None
    bcc: str | list[str] | None = None


class EmailResponse(BaseModel):
    success: bool
    message: str


@app.get("/", status_code=200, tags=["Health"])
def greeting():
    """
    Health check endpoint that returns a greeting message.
    """
    return "Hello from portal-conductor."


@app.post(
    "/users", status_code=200, response_model=UserResponse, tags=["User Management"]
)
def add_user(user: portal_ldap.CreateUserRequest):
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
    try:
        print(f"Creating LDAP user: {user.username}", file=sys.stderr)
        ldap_api.create_user(user)

        print(f"Setting LDAP password for: {user.username}", file=sys.stderr)
        ldap_api.change_password(user.username, user.password)

        print(
            f"Adding user {user.username} to everyone group: {ldap_everyone_group}",
            file=sys.stderr,
        )
        ldap_api.add_user_to_group(user.username, ldap_everyone_group)

        print(
            f"Adding user {user.username} to community group: {ldap_community_group}",
            file=sys.stderr,
        )
        ldap_api.add_user_to_group(user.username, ldap_community_group)

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
        import traceback

        print(f"Traceback: {traceback.format_exc()}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"User creation failed: {str(e)}")


@app.post(
    "/users/{username}/password",
    status_code=200,
    response_model=UserResponse,
    tags=["User Management"],
)
def change_password(username: str, request: PasswordChangeRequest):
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
    ldap_api.change_password(username, request.password)
    ldap_api.shadow_last_change(username)
    ds_api.change_password(username, request.password)
    return {"user": username}


@app.delete(
    "/users/{username}",
    status_code=200,
    response_model=UserResponse,
    tags=["User Management"],
)
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
    print(f"Deleting LDAP user: {username}")
    user_groups = ldap_api.get_user_groups(username)
    print(f"User {username} is in groups: {user_groups}", file=sys.stderr)
    for ug in user_groups:
        group_name = ug[1]["cn"][0]
        print(f"Removing user {username} from group {group_name}", file=sys.stderr)
        ldap_api.remove_user_from_group(username, group_name)
        print(f"Removed user {username} from group {group_name}", file=sys.stderr)
    print(f"Deleting user {username} from LDAP", file=sys.stderr)
    ldap_api.delete_user(username)
    print(f"Deleted LDAP user: {username}", file=sys.stderr)
    return {"user": username}


@app.delete(
    "/emails/lists/{list_name}/addresses/{addr}",
    status_code=200,
    response_model=EmailListResponse,
    tags=["Email Management"],
)
def remove_addr_from_list(list_name: str, addr: str):
    """
    Remove an email address from a mailing list.

    If Mailman integration is enabled, removes the specified email address
    from the given mailing list.

    Args:
        list_name: The name of the mailing list
        addr: The email address to remove

    Returns:
        EmailListResponse: Confirmation with list name and email address

    Raises:
        HTTPException: If removal fails or list doesn't exist
    """
    if mailman_enabled:
        email_api.remove_member(list_name, addr)
    return {"list": list_name, "email": addr}


@app.post(
    "/emails/lists/{list_name}/addresses/{addr}",
    status_code=200,
    response_model=EmailListResponse,
    tags=["Email Management"],
)
def add_addr_to_list(list_name: str, addr: str):
    """
    Add an email address to a mailing list.

    If Mailman integration is enabled, adds the specified email address
    to the given mailing list.

    Args:
        list_name: The name of the mailing list
        addr: The email address to add

    Returns:
        EmailListResponse: Confirmation with list name and email address

    Raises:
        HTTPException: If addition fails or list doesn't exist
    """
    if mailman_enabled:
        email_api.add_member(list_name, addr)
    return {"list": list_name, "email": addr}


def set_vice_job_limit(request: ServiceRegistrationRequest):
    token = terrain_api.get_keycloak_token()
    terrain_api.set_concurrent_job_limits(
        token=token, username=request.user.username, limit="2"
    )


services_config = {
    "COGE": {
        "irods_path": "coge_data",
    },
    "DISCOVERY_ENVIRONMENT": {
        "ldap_group": "de-preview-access",
        "mailing_list": ["de-users", "datastore-users"],
    },
    "SCI_APPS": {
        "irods_path": "sci_data",
        "irods_user": "maizecode",
    },
    "VICE": {
        "custom_action": set_vice_job_limit,
    },
}


@app.get(
    "/services/approval-keys",
    status_code=200,
    response_model=ServiceKeysResponse,
    tags=["Service Management"],
)
def service_names():
    """
    Get list of available service approval keys.

    Returns the list of valid approval keys that can be used for
    service registration.

    Returns:
        ServiceKeysResponse: List of available approval keys
    """
    return {"approval_keys": list(services_config.keys())}


@app.post(
    "/services/register",
    status_code=200,
    response_model=ServiceRegistrationResponse,
    tags=["Service Management"],
)
def service_registration(request: ServiceRegistrationRequest):
    """
    Register a user for a specific CyVerse service.

    This endpoint handles service-specific user registration by:
    - Adding users to required LDAP groups
    - Setting up iRODS paths and permissions
    - Adding users to mailing lists
    - Executing custom actions (like setting VICE job limits)

    Available services:
    - COGE: Sets up coge_data iRODS path
    - DISCOVERY_ENVIRONMENT: Adds to de-preview-access group and mailing lists
    - SCI_APPS: Sets up sci_data iRODS path with maizecode user
    - VICE: Sets concurrent job limits via custom action

    Args:
        request: Service registration request containing user info and approval key

    Returns:
        ServiceRegistrationResponse: Details of what was configured for the user

    Raises:
        HTTPException: If approval key is invalid or user information is missing
    """
    retval = {}

    approval_key = request.service.approval_key
    if approval_key not in services_config:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service approval key: {approval_key}",
        )

    user = request.user
    if user is None or user.username is None:
        raise HTTPException(
            status_code=400,
            detail="User information is required for service registration.",
        )

    svc_cfg = services_config[approval_key]

    retval["user"] = user.username
    retval["service"] = approval_key

    if "ldap_group" in svc_cfg:
        user_groups = list(
            map(lambda g: g[1]["cn"][0], ldap_api.get_user_groups(user.username))
        )
        if svc_cfg["ldap_group"] not in user_groups:
            ldap_api.add_user_to_group(user.username, svc_cfg["ldap_group"])
        retval["ldap_group"] = svc_cfg["ldap_group"]

    if "irods_path" in svc_cfg:
        ds_api.register_service(
            username=user.username,
            irods_path=svc_cfg["irods_path"],
            irods_user=svc_cfg["irods_user"] if "irods_user" in svc_cfg else None,
        )
        retval["irods_path"] = svc_cfg["irods_path"]
        if "irods_user" in svc_cfg:
            retval["irods_user"] = svc_cfg["irods_user"]

    if "mailing_list" in svc_cfg and mailman_enabled:
        mailing_lists = svc_cfg["mailing_list"]
        if isinstance(mailing_lists, str):
            mailing_lists = [mailing_lists]
        for ml in mailing_lists:
            email_api.add_member(ml, user.email)
        retval["mailing_list"] = mailing_lists

    if "custom_action" in svc_cfg:
        custom_actions = svc_cfg["custom_action"]
        if not isinstance(custom_actions, list):
            custom_actions = [custom_actions]
        for ca in custom_actions:
            if callable(ca):
                ca(request)
        retval["custom_action"] = "completed"

    return retval


@app.post(
    "/emails/send",
    status_code=200,
    response_model=EmailResponse,
    tags=["Email Management"],
)
def send_email(request: EmailRequest):
    """
    Send an email via SMTP.

    This endpoint provides email sending functionality to replace direct
    sendmail usage in the portal. It supports both text and HTML email
    bodies, BCC recipients, and configurable sender addresses.

    Args:
        request: Email request containing recipient(s), subject, body, and optional fields

    Returns:
        EmailResponse: Success status and message

    Raises:
        HTTPException: If email sending fails or required fields are missing
    """
    if not request.text_body and not request.html_body:
        raise HTTPException(
            status_code=400, detail="Either text_body or html_body must be provided"
        )

    success = smtp_service.send_email(
        to=request.to,
        subject=request.subject,
        text_body=request.text_body,
        html_body=request.html_body,
        from_email=request.from_email,
        bcc=request.bcc,
    )

    if success:
        return {"success": True, "message": "Email sent successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email")
