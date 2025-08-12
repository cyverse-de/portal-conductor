import os
import portal_ldap
import portal_datastore

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

portal_ldap_url = "http://portal-ldap/"
portal_ldap_env = os.environ.get("PORTAL_LDAP_URL")
if portal_ldap_env is not None:
    portal_ldap_url = portal_ldap_env

portal_datastore_url = "http://portal-datastore/"
portal_datastore_env = os.environ.get("PORTAL_DATASTORE_URL")
if portal_datastore_env is not None:
    portal_datastore_url = portal_datastore_env


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
    # Create the user in ldap_api
    # Change the password for some reason
    # Add the user to the everyone group
    # Add the user to the community group
    # Create the Data Store user
    # Change the Data Store password
    # Grant access to the user's home directory to the ipcservices user
    # Grant access to the user's home directory to the rodsadmin
    # Subscribe the user to the newsletter


@app.post("/users/{username}/password", status_code=200)
def change_password(username: str, password: str):
    # Change the user's password in LDAP
    # Shadow the last change
    # Set the password in the data store.


@app.delete("/user/{username}", status_code=200)
def delete_user(username: str):
    # Remove the user from any groups that it's in.
    # Remove the LDAP user.
