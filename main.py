import json
import os
import sys
import traceback

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import email_service
import formation
import mailman
import portal_datastore
import portal_ldap
import terrain
from handlers import dependencies
from handlers import user_management
from handlers import ldap_management
from handlers import email_management
from handlers import mailing_list_management
from handlers import datastore_management
from handlers import terrain_management


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
        },
        "formation": {
            "base_url": os.environ.get("FORMATION_URL", ""),
            "keycloak": {
                "server_url": os.environ.get("KEYCLOAK_SERVER_URL", ""),
                "realm": os.environ.get("KEYCLOAK_REALM", ""),
                "client_id": os.environ.get("KEYCLOAK_CLIENT_ID", ""),
                "client_secret": os.environ.get("KEYCLOAK_CLIENT_SECRET", "")
            },
            "user_deletion_app_id": os.environ.get("FORMATION_USER_DELETION_APP_ID", ""),
            "user_deletion_app_name": os.environ.get("FORMATION_USER_DELETION_APP_NAME", "portal-delete-user"),
            "system_id": os.environ.get("FORMATION_SYSTEM_ID", "de"),
            "verify_ssl": os.environ.get("FORMATION_VERIFY_SSL", "true").lower() in ["1", "true", "yes"]
        }
    }

    return config


# Load configuration
config = load_config()

# Extract SSL configuration
ssl_enabled = config.get("ssl", {}).get("enabled", False)
ssl_cert_file = config.get("ssl", {}).get("cert_file")
ssl_key_file = config.get("ssl", {}).get("key_file")
ssl_port = config.get("ssl", {}).get("port", 8443)
http_port = config.get("server", {}).get("http_port", 8000)

# Extract authentication configuration
auth_enabled = config.get("auth", {}).get("enabled", True)
auth_realm = config.get("auth", {}).get("realm", "Portal Conductor API")

# Configure API description based on auth status
api_description = """
API for managing user accounts, email lists, and service registrations in the CyVerse platform.

## Features

- **User Management**: Create and manage LDAP users with group memberships
- **DataStore Integration**: Set up iRODS users with permissions
- **Terrain Integration**: Manage VICE job limits
- **Mailing Lists**: Manage Mailman subscriptions
- **Async Operations**: Formation-powered batch jobs for long-running operations

## Async User Deletion

For users with large home directories, use the async deletion endpoints under **Async Operations**:
1. `DELETE /async/users/{username}` - Submit deletion job
2. `GET /async/status/{analysis_id}` - Track job progress

These endpoints use the Formation batch job service to handle operations that may take several minutes.
"""

if auth_enabled:
    api_description += "\n\n**Authentication Required**: This API uses HTTP Basic Authentication. Use the 'Authorize' button below to provide credentials."

app = FastAPI(
    title="Portal Conductor API",
    description=api_description,
    version="1.0.0",
    contact={
        "name": "CyVerse Support",
        "url": "https://cyverse.org",
    },
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException):
    """Handle standard HTTP exceptions."""
    print(exc, file=sys.stderr)
    return JSONResponse(
        content={"detail": exc.detail},
        status_code=exc.status_code
    )


@app.exception_handler(httpx.HTTPStatusError)
async def httpx_exception_handler(_: Request, exc: httpx.HTTPStatusError):
    """Handle HTTP errors from external services (Formation, etc.)."""
    status_code = exc.response.status_code

    # Log the error
    print(
        f"External API error: {status_code} - {exc.request.url}",
        file=sys.stderr
    )
    try:
        error_detail = exc.response.text
        print(f"Response: {error_detail}", file=sys.stderr)
    except Exception:
        pass

    # Pass through 404s, convert everything else to 502 (Bad Gateway)
    if status_code == 404:
        return JSONResponse(
            content={"detail": "Resource not found in external service"},
            status_code=404
        )
    return JSONResponse(
        content={"detail": f"External service error: {status_code}"},
        status_code=502
    )


@app.exception_handler(httpx.RequestError)
async def httpx_request_error_handler(_: Request, exc: httpx.RequestError):
    """Handle network/connection errors to external services."""
    print(f"Request error: {exc}", file=sys.stderr)
    return JSONResponse(
        content={"detail": "Failed to connect to external service"},
        status_code=503
    )


@app.middleware("http")
async def exception_handling_middleware(request: Request, call_next):
    """Middleware to handle all unhandled exceptions."""
    try:
        return await call_next(request)
    except Exception as e:
        # Log full traceback for unexpected errors
        print(
            f"Unhandled exception: {type(e).__name__}: {e}",
            file=sys.stderr
        )
        print(traceback.format_exc(), file=sys.stderr)
        return JSONResponse(
            content={"detail": "Internal server error"},
            status_code=500
        )


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
mailman_url = config["mailman"]["url"]
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
formation_config = config.get("formation", {})
formation_base_url = formation_config.get("base_url", "")
formation_keycloak_config = formation_config.get("keycloak", {})
formation_keycloak_url = formation_keycloak_config.get("server_url", "")
formation_keycloak_realm = formation_keycloak_config.get("realm", "")
formation_keycloak_client_id = formation_keycloak_config.get("client_id", "")
formation_keycloak_client_secret = formation_keycloak_config.get("client_secret", "")
formation_app_id = formation_config.get("user_deletion_app_id", "")
formation_app_name = formation_config.get("user_deletion_app_name", "portal-delete-user")
formation_system_id = formation_config.get("system_id", "de")
formation_verify_ssl = formation_config.get("verify_ssl", True)
formation_timeout = formation_config.get("timeout", 60.0)


# Initialize direct connections
ldap_conn = portal_ldap.connect(ldap_url, ldap_user, ldap_password)
ds_api = portal_datastore.DataStore(irods_host, irods_port, irods_user, irods_password, irods_zone)
terrain_api = terrain.Terrain(
    api_url=terrain_url, username=terrain_user, password=terrain_password
)
email_api = mailman.Mailman(api_url=mailman_url, password=mailman_password)
smtp_service = email_service.EmailService(config)
formation_api = None
if (formation_base_url and formation_keycloak_url and
    formation_keycloak_realm and formation_keycloak_client_id and
    formation_keycloak_client_secret):
    formation_api = formation.Formation(
        api_url=formation_base_url,
        keycloak_url=formation_keycloak_url,
        realm=formation_keycloak_realm,
        client_id=formation_keycloak_client_id,
        client_secret=formation_keycloak_client_secret,
        verify_ssl=formation_verify_ssl,
        timeout=formation_timeout,
    )

    # Look up app ID by name at startup if only name is provided
    if formation_api and not formation_app_id and formation_app_name:
        print(f"Looking up Formation app ID for '{formation_app_name}' in system '{formation_system_id}'", file=sys.stderr)
        try:
            formation_app_id = formation_api.get_app_id_by_name(formation_system_id, formation_app_name)
            if formation_app_id:
                print(f"Found app ID: {formation_app_id}", file=sys.stderr)
            else:
                print(f"WARNING: Could not find app with name '{formation_app_name}' in system '{formation_system_id}'", file=sys.stderr)
                print("User deletion will not work until app is created or app_id is configured", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: Failed to lookup app ID for '{formation_app_name}': {e}", file=sys.stderr)
            print("User deletion will not work until app is created or app_id is configured", file=sys.stderr)

# Initialize dependencies for handlers
dependencies.init_dependencies(
    config=config,
    ldap_conn=ldap_conn,
    ds_api=ds_api,
    terrain_api=terrain_api,
    email_api=email_api,
    smtp_service=smtp_service,
    ldap_community_group=ldap_community_group,
    ldap_everyone_group=ldap_everyone_group,
    ipcservices_user=ipcservices_user,
    ds_admin_user=ds_admin_user,
    terrain_url=terrain_url,
    terrain_user=terrain_user,
    terrain_password=terrain_password,
    mailman_enabled=mailman_enabled,
    mailman_url=mailman_url,
    mailman_password=mailman_password,
    ldap_url=ldap_url,
    ldap_user=ldap_user,
    ldap_password=ldap_password,
    ldap_base_dn=ldap_base_dn,
    irods_host=irods_host,
    irods_port=irods_port,
    irods_user=irods_user,
    irods_password=irods_password,
    irods_zone=irods_zone,
    formation_api=formation_api,
    formation_app_id=formation_app_id,
    formation_app_name=formation_app_name,
    formation_system_id=formation_system_id,
)



@app.get("/", status_code=200, tags=["Health"])
def greeting():
    """
    Health check endpoint that returns a greeting message.

    This endpoint is intentionally unauthenticated to allow health checks
    from monitoring systems and load balancers.
    """
    return "Hello from portal-conductor."


# Register all handler routers
app.include_router(user_management.router)
app.include_router(user_management.async_router)
app.include_router(ldap_management.router)
app.include_router(email_management.router)
app.include_router(mailing_list_management.router)
app.include_router(datastore_management.router)
app.include_router(terrain_management.router)


