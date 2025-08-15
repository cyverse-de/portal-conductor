import os
import portal_ldap
import portal_datastore

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ldap import LDAPError

app = FastAPI()

portal_ldap_url = "http://portal-ldap/"
portal_ldap_env = os.environ.get("PORTAL_LDAP_URL")
if portal_ldap_env is not None:
    portal_ldap_url = portal_ldap_env

portal_datastore_url = "http://portal-datastore/"
portal_datastore_env = os.environ.get("PORTAL_DATASTORE_URL")
if portal_datastore_env is not None:
    portal_datastore_url = portal_datastore_env

ldap_everyone_group = os.environ.get("LDAP_EVERYONE_GROUP")
if ldap_everyone_group is None:
    print("LDAP_EVERYONE_GROUP must be set", file=sys.stderr)
    os.exit(1)

ldap_community_group = "community"
ldap_community_group_env = os.environ.get("LDAP_COMMUNITY_GROUP")
if ldap_community_group_env is not None:
    ldap_community_group = ldap_community_group_env

ipcservices_user = "ipcservices"
ipcservices_user_env = os.environ.get("IPCSERVICES_USER")
if ipcservices_user_env is not None:
    ipcservices_user = ipcservices_user_env

ds_admin_user = "rodsadmin"
ds_admin_user_env = os.environ.get("DS_ADMIN_USER")
if ds_admin_user_env is not None:
    ds_admin_user = ds_admin_user_env

ldap_api = portal_ldap.LDAP(portal_ldap_url)
ds_api = portal_datastore.DataStore(portal_datastore_url)


class CreateUserRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    username: str
    user_uid: str
    password: str
    department: str
    organization: str
    title: str


@app.post("/users", status_code=200)
def add_user(user: CreateUserRequest):
    try:
        new_user = ldap_api.create_user(user)
        ldap_api.change_password(user.username, user.password)
        ldap_api.add_user_to_group(user.username, ldap_everyone_group)
        ldap_api.add_user_to_group(user.username, ldap_community_group)
        ds_api.create_user(user.username)
        ds_api.change_password(user.username, user.password)
        home_dir = ds_api.user_home(user.username)
        ipcservices_perm = portal_datastore.PathPermission(
            username=ipcservices_user,
            permissions="own",
            path=home_dir,
        )
        rodsadmin_perm = portal_datastore.PathPermission(
            username=rodsadmin_perm,
            permissions="own",
            path=home_dir,
        )
        ds_api.chmod(ipcservices_perm)
        ds_api.chmod(rodsadmin_perm)
    except Exception as err:
        raise HTTPException(500, err)


@app.post("/users/{username}/password", status_code=200)
def change_password(username: str, password: str):
    try:
        ldap_api.change_password(username, password)
        ldap_api.shadow_last_change(username)
        ds_api.change_password(username, password)
    except Exception as err:
        raise HTTPException(500, err)


@app.delete("/user/{username}", status_code=200)
def delete_user(username: str):
    try:
        user_groups = ldap_api.get_user_groups(username)
        for ug in user_groups:
            group_name = ug[1]["cn"]
            ldap_api.remove_user_from_group(username, group_name)
        ldap_api.delete_user(username)
    except Exception as err:
        raise HTTPException(500, err)
