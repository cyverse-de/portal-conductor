import json
import os
import sys

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
            "system_id": os.environ.get("FORMATION_SYSTEM_ID", "de")
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
api_description = "API for managing user accounts, email lists, and service registrations in the CyVerse platform"
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
    )

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


