import os
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

import mailman
import portal_datastore
import portal_ldap
import terrain

app = FastAPI()


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


@app.get("/", status_code=200)
def greeting():
    return "Hello from portal-conductor."


@app.post("/users", status_code=200)
def add_user(user: portal_ldap.CreateUserRequest):
    ldap_api.create_user(user)
    ldap_api.change_password(user.username, user.password)
    ldap_api.add_user_to_group(user.username, ldap_everyone_group)
    ldap_api.add_user_to_group(user.username, ldap_community_group)
    ds_api.create_user(user.username)
    ds_api.change_password(user.username, user.password)
    home_dir = ds_api.user_home(user.username)
    ipcservices_perm = portal_datastore.PathPermission(
        username=ipcservices_user,
        permission="own",
        path=home_dir,
    )
    rodsadmin_perm = portal_datastore.PathPermission(
        username=ds_admin_user,
        permission="own",
        path=home_dir,
    )
    ds_api.chmod(ipcservices_perm)
    ds_api.chmod(rodsadmin_perm)
    return {"user": user.username}


@app.post("/users/{username}/password", status_code=200)
def change_password(username: str, password: str):
    ldap_api.change_password(username, password)
    ldap_api.shadow_last_change(username)
    ds_api.change_password(username, password)
    return {"user": username}


@app.delete("/users/{username}", status_code=200)
def delete_user(username: str):
    user_groups = ldap_api.get_user_groups(username)
    for ug in user_groups:
        group_name = ug[1]["cn"][0]
        ldap_api.remove_user_from_group(username, group_name)
    ldap_api.delete_user(username)
    return {"user": username}


@app.delete("/emails/lists/{list_name}/addresses/{addr}", status_code=200)
def remove_addr_from_list(list_name: str, addr: str):
    if mailman_enabled:
        email_api.remove_member(list_name, addr)
    return {"list": list_name, "email": addr}


@app.post("/emails/lists/{list_name}/addresses/{addr}", status_code=200)
def add_addr_to_list(list_name: str, addr: str):
    if mailman_enabled:
        email_api.add_member(list_name, addr)
    return {"list": list_name, "email": addr}


class ServiceRegistrationUser(BaseModel):
    username: str
    email: str


class ServiceRegistrationService(BaseModel):
    approval_key: str


class ServiceRegistrationRequest(BaseModel):
    user: ServiceRegistrationUser
    service: ServiceRegistrationService


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


@app.get("/services/approval-keys", status_code=200)
def service_names():
    return {"approval_keys": list(services_config.keys())}


@app.post("/services/register", status_code=200)
def service_registration(request: ServiceRegistrationRequest):
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
