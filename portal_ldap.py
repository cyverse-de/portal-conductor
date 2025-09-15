import functools
import os.path
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel


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


class LDAP(object):
    def __init__(self, api_url: str, timeout: float = 20.0):
        self.base_url = api_url
        self.timeout = timeout

    def api_url(self, *parts: str):
        part_path = functools.reduce(os.path.join, parts, "/")
        return urljoin(self.base_url, part_path)

    def create_user(self, req: CreateUserRequest) -> map:
        r = httpx.post(self.api_url("users"), json=req.model_dump(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def list_users(self) -> map:
        r = httpx.get(self.api_url("users"), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def list_groups(self) -> map:
        r = httpx.get(self.api_url("groups"), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_user(self, username: str) -> map:
        r = httpx.get(self.api_url("users", username), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_user_groups(self, username: str) -> list[list]:
        r = httpx.get(self.api_url("users", username, "groups"), timeout=self.timeout)
        r.raise_for_status()
        return r.json()["groups"]

    def add_user_to_group(self, username: str, group: str) -> map:
        r = httpx.post(self.api_url("groups", group, "users", username), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def remove_user_from_group(self, username: str, group: str) -> map:
        r = httpx.delete(self.api_url("groups", group, "users", username), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def delete_user(self, username: str) -> map:
        r = httpx.delete(self.api_url("users", username), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def change_password(self, username: str, password: str) -> map:
        r = httpx.put(
            self.api_url("users", username, "password"),
            json={"password": password},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def shadow_last_change(self, username: str) -> map:
        r = httpx.post(self.api_url("users", username, "shadow-last-change"), timeout=self.timeout)
        r.raise_for_status()
        return r.json()
