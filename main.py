import json
import os
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

import email_service
import kinds
import mailman
import portal_datastore
import portal_ldap
import terrain


def load_config():
    """Load configuration from JSON file or environment variables as fallback."""
    config_file = os.environ.get("PORTAL_CONDUCTOR_CONFIG", "config.json")

    # Try to load from JSON file first
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                print(f"Loaded configuration from {config_file}", file=sys.stderr)
                return config
        except Exception as e:
            print(f"Failed to load config from {config_file}: {e}", file=sys.stderr)
            print("Falling back to environment variables", file=sys.stderr)

    # Fallback to environment variables
    config = {
        "ldap": {
            "url": os.environ.get("LDAP_URL", ""),
            "user": os.environ.get("LDAP_USER", ""),
            "password": os.environ.get("LDAP_PASSWORD", ""),
            "base_dn": os.environ.get("LDAP_BASE_DN", ""),
            "community_group": os.environ.get("LDAP_COMMUNITY_GROUP", "community"),
            "everyone_group": os.environ.get("LDAP_EVERYONE_GROUP", "")
        },
        "irods": {
            "host": os.environ.get("IRODS_HOST", ""),
            "port": os.environ.get("IRODS_PORT", ""),
            "user": os.environ.get("IRODS_USER", ""),
            "password": os.environ.get("IRODS_PASSWORD", ""),
            "zone": os.environ.get("IRODS_ZONE", ""),
            "admin_user": os.environ.get("DS_ADMIN_USER", "rodsadmin"),
            "ipcservices_user": os.environ.get("IPCSERVICES_USER", "ipcservices")
        },
        "terrain": {
            "url": os.environ.get("TERRAIN_URL", "http://terrain/"),
            "user": os.environ.get("TERRAIN_USER", ""),
            "password": os.environ.get("TERRAIN_PASSWORD", "")
        },
        "mailman": {
            "enabled": os.environ.get("MAILMAN_ENABLED", "false").lower() in ["1", "true", "yes"],
            "url": os.environ.get("MAILMAN_URL", ""),
            "password": os.environ.get("MAILMAN_PASSWORD", "")
        }
    }

    return config


# Load configuration
config = load_config()

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
async def http_exception_handler(_: Request, exc: StarletteHTTPException):
    print(exc, file=sys.stderr)
    return JSONResponse(content={"detail": exc.detail}, status_code=exc.status_code)


@app.middleware("http")
async def exception_handling_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return JSONResponse(content=str(e), status_code=500)


# Validate required configuration
def validate_config(config):
    """Validate that all required configuration values are present."""
    required_fields = [
        ("ldap.url", config["ldap"]["url"]),
        ("ldap.user", config["ldap"]["user"]),
        ("ldap.password", config["ldap"]["password"]),
        ("ldap.base_dn", config["ldap"]["base_dn"]),
        ("ldap.everyone_group", config["ldap"]["everyone_group"]),
        ("irods.host", config["irods"]["host"]),
        ("irods.port", config["irods"]["port"]),
        ("irods.user", config["irods"]["user"]),
        ("irods.password", config["irods"]["password"]),
        ("irods.zone", config["irods"]["zone"]),
        ("terrain.user", config["terrain"]["user"]),
        ("terrain.password", config["terrain"]["password"]),
    ]

    if config["mailman"]["enabled"]:
        required_fields.extend([
            ("mailman.url", config["mailman"]["url"]),
            ("mailman.password", config["mailman"]["password"]),
        ])

    for field_name, field_value in required_fields:
        if not field_value:
            print(f"Required configuration field '{field_name}' is not set", file=sys.stderr)
            sys.exit(1)

    if not config["mailman"]["enabled"]:
        print("MAILMAN_ENABLED is not set to true, mailman integration disabled")

validate_config(config)

# Extract configuration values for easier access
ldap_community_group = config["ldap"]["community_group"]
ldap_everyone_group = config["ldap"]["everyone_group"]
ipcservices_user = config["irods"]["ipcservices_user"]
ds_admin_user = config["irods"]["admin_user"]
terrain_url = config["terrain"]["url"]
terrain_user = config["terrain"]["user"]
terrain_password = config["terrain"]["password"]
mailman_enabled = config["mailman"]["enabled"]
mailmain_url = config["mailman"]["url"]
mailman_password = config["mailman"]["password"]
ldap_url = config["ldap"]["url"]
ldap_user = config["ldap"]["user"]
ldap_password = config["ldap"]["password"]
ldap_base_dn = config["ldap"]["base_dn"]
irods_host = config["irods"]["host"]
irods_port = config["irods"]["port"]
irods_user = config["irods"]["user"]
irods_password = config["irods"]["password"]
irods_zone = config["irods"]["zone"]


# Initialize direct connections
ldap_conn = portal_ldap.connect(ldap_url, ldap_user, ldap_password)
ds_api = portal_datastore.DataStore(irods_host, irods_port, irods_user, irods_password, irods_zone)
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


class DatastoreServiceRequest(BaseModel):
    irods_path: str
    irods_user: str | None = None


class MailingListMemberRequest(BaseModel):
    email: str


class JobLimitsRequest(BaseModel):
    limit: int


class GenericResponse(BaseModel):
    success: bool
    message: str


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
    portal_ldap.change_password(ldap_conn, ldap_base_dn, username, request.password)
    dse = portal_ldap.days_since_epoch()
    portal_ldap.shadow_last_change(ldap_conn, ldap_base_dn, dse, username)
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


# Granular service registration endpoints for improved architecture


@app.post(
    "/ldap/users/{username}/groups/{groupname}",
    status_code=200,
    response_model=GenericResponse,
    tags=["LDAP Management"],
)
def add_user_to_ldap_group(username: str, groupname: str):
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
    try:
        # Check if user is already in group
        user_groups = list(
            map(lambda g: g[1]["cn"][0], portal_ldap.get_user_groups(ldap_conn, ldap_base_dn, username))
        )
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
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to add user to LDAP group: {str(e)}"
        )


@app.get(
    "/ldap/users/{username}/groups",
    status_code=200,
    response_model=list[str],
    tags=["LDAP Management"],
)
def get_user_ldap_groups(username: str):
    """
    Get all LDAP groups for a user.

    Args:
        username: Username to lookup

    Returns:
        list[str]: List of group names the user belongs to

    Raises:
        HTTPException: If operation fails
    """
    try:
        user_groups = list(
            map(lambda g: g[1]["cn"][0], portal_ldap.get_user_groups(ldap_conn, ldap_base_dn, username))
        )
        return user_groups
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get user LDAP groups: {str(e)}"
        )


@app.delete(
    "/ldap/users/{username}/groups/{groupname}",
    status_code=200,
    response_model=GenericResponse,
    tags=["LDAP Management"],
)
def remove_user_from_ldap_group(username: str, groupname: str):
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
    try:
        portal_ldap.remove_user_from_group(ldap_conn, ldap_base_dn, username, groupname)
        return {
            "success": True,
            "message": f"User {username} removed from group {groupname}",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to remove user from LDAP group: {str(e)}"
        )


@app.post(
    "/datastore/users/{username}/services",
    status_code=200,
    response_model=GenericResponse,
    tags=["DataStore Management"],
)
def register_datastore_service(username: str, request: DatastoreServiceRequest):
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


@app.post(
    "/mailinglists/{listname}/members",
    status_code=200,
    response_model=GenericResponse,
    tags=["Mailing List Management"],
)
def add_to_mailing_list(listname: str, request: MailingListMemberRequest):
    """
    Add a user to a mailing list.

    Args:
        listname: Mailing list name
        request: Member details

    Returns:
        GenericResponse: Success status and message

    Raises:
        HTTPException: If operation fails or mailman not enabled
    """
    if not mailman_enabled:
        raise HTTPException(
            status_code=503, detail="Mailing list functionality is not enabled"
        )

    try:
        email_api.add_member(listname, request.email)
        return {
            "success": True,
            "message": f"Added {request.email} to mailing list {listname}",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to add user to mailing list: {str(e)}"
        )


@app.delete(
    "/mailinglists/{listname}/members/{email}",
    status_code=200,
    response_model=GenericResponse,
    tags=["Mailing List Management"],
)
def remove_from_mailing_list(listname: str, email: str):
    """
    Remove a user from a mailing list.

    Args:
        listname: Mailing list name
        email: Email address to remove

    Returns:
        GenericResponse: Success status and message

    Raises:
        HTTPException: If operation fails or mailman not enabled
    """
    if not mailman_enabled:
        raise HTTPException(
            status_code=503, detail="Mailing list functionality is not enabled"
        )

    try:
        email_api.remove_member(listname, email)
        return {
            "success": True,
            "message": f"Removed {email} from mailing list {listname}",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to remove user from mailing list: {str(e)}"
        )


@app.post(
    "/terrain/users/{username}/job-limits",
    status_code=200,
    response_model=GenericResponse,
    tags=["Terrain Management"],
)
def set_job_limits(username: str, request: JobLimitsRequest):
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
