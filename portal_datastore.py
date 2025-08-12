import httpx
import functools
import os.path

from urllib.parse import urljoin
from pydantic import BaseModel

class PathPermission(BaseModel):
    username: str
    path: str
    permission: str

class DataStore(object):
    def __init__(self, api_url: str):
        self.base_url = api_url

    def _url_join(self, parts: list[str]) -> str:
        part_path = functools.reduce(os.path.join, parts, "/")
        return urljoin(self.base_url, part_path)

    def list_available_permissions(self) -> list[str]:
        r = httpx.get(self._url_join(["permissions", "available"]))
        r.raise_for_status()
        body = r.json()
        return body["permissions"]

    def path_exists(self, path: str) -> bool:
        r = httpx.get(self._url_join(["path", "exists"]), params={"path":path})
        r.raise_for_status()
        body = r.json()
        return body["exists"]

    def path_permissions(self, path: str) -> list[object]:
        r = httpx.get(self._url_join(["path", "permissions"]), params={"path":path})
        r.raise_for_status()
        body = r.json()
        return body["permissions"]

    def user_exists(self, username: str) -> bool:
        r = httpx.get(self._url_join(["users", username, "exists"]))
        r.raise_for_status()
        body = r.json()
        return body["exists"]

    def create_user(self, username: str):
        r = httpx.post(self._url_join(["users", username]))
        r.raise_for_status()
        return r.json()

    def delete_user(self, username: str):
        r = httpx.delete(self._url_join(["users", username]))
        r.raise_for_status()
        return r.json()

    def delete_home(self, username: str):
        r = httpx.delete(self._url_join(["users", username, "home"]))
        r.raise_for_status()
        return r.json()

    def change_password(self, username: str, new_password):
        r = httpx.post(self._url_join(["users", username, "password"]), json={"password":new_password})
        r.raise_for_status()
        return r.json()

    def chmod(self, perm: PathPermission):
        r = httpx.post(self._url_join(["path", "chmod"]), json=perm.model_dump())
        r.raise_for_status()
        return r.json()
