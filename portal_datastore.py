import functools
import os.path
import sys
from urllib.parse import urljoin

import httpx
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

    def _log_http_error(self, error: httpx.HTTPStatusError, operation: str, context: str = "") -> None:
        """Log HTTPStatusError with detailed information including response body."""
        error_detail = f"DataStore {operation} failed{f' {context}' if context else ''}: {error.response.status_code} {error.response.reason_phrase}"
        try:
            error_body = error.response.text
            if error_body:
                error_detail += f" - Response: {error_body}"
        except:
            pass
        print(f"DataStore API Error: {error_detail}", file=sys.stderr)

    def health_check(self) -> bool:
        """
        Check if the datastore service is reachable and healthy.
        
        Returns:
            bool: True if the service is healthy, False otherwise
        """
        try:
            print(f"Checking datastore service health at: {self.base_url}", file=sys.stderr)
            response = httpx.get(self.base_url.rstrip('/'), timeout=5.0)
            print(f"Datastore health check: {response.status_code}", file=sys.stderr)
            return response.status_code < 400
        except Exception as health_error:
            print(f"Datastore health check failed: {type(health_error).__name__}: {health_error}", file=sys.stderr)
            return False

    def list_available_permissions(self) -> list[str]:
        r = httpx.get(self._url_join(["permissions", "available"]))
        r.raise_for_status()
        body = r.json()
        return body["permissions"]

    def path_exists(self, path: str) -> bool:
        r = httpx.get(self._url_join(["path", "exists"]), params={"path": path})
        r.raise_for_status()
        body = r.json()
        return body["exists"]

    def path_permissions(self, path: str) -> list[object]:
        r = httpx.get(self._url_join(["path", "permissions"]), params={"path": path})
        r.raise_for_status()
        body = r.json()
        return body["permissions"]

    def user_exists(self, username: str) -> bool:
        r = httpx.get(self._url_join(["users", username, "exists"]))
        r.raise_for_status()
        body = r.json()
        return body["exists"]

    def create_user(self, username: str):
        url = self._url_join(["users", username])
        try:
            r = httpx.post(url)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            self._log_http_error(e, "create_user", f"for '{username}'")
            raise
        except Exception as e:
            print(
                f"DataStore connection error for create_user('{username}'): {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            raise

    def user_home(self, username: str):
        url = self._url_join(["users", username, "home"])
        try:
            r = httpx.get(url)
            r.raise_for_status()
            return r.json()["home"]
        except httpx.HTTPStatusError as e:
            self._log_http_error(e, "user_home", f"for '{username}'")
            raise
        except Exception as e:
            print(
                f"DataStore connection error for user_home('{username}'): {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            raise

    def delete_user(self, username: str):
        r = httpx.delete(self._url_join(["users", username]))
        r.raise_for_status()
        return r.json()

    def delete_home(self, username: str):
        r = httpx.delete(self._url_join(["users", username, "home"]))
        r.raise_for_status()
        return r.json()

    def change_password(self, username: str, new_password):
        url = self._url_join(["users", username, "password"])
        try:
            r = httpx.post(url, json={"password": new_password})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            self._log_http_error(e, "change_password", f"for '{username}'")
            raise
        except Exception as e:
            print(
                f"DataStore connection error for change_password('{username}'): {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            raise

    def chmod(self, perm: PathPermission):
        url = self._url_join(["path", "chmod"])
        try:
            r = httpx.post(url, json=perm.model_dump())
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            self._log_http_error(e, "chmod", f"for '{perm.username}' on '{perm.path}'")
            raise
        except Exception as e:
            print(
                f"DataStore connection error for chmod('{perm.path}'): {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            raise

    def register_service(
        self, username: str, irods_path: str, irods_user: str | None = None
    ):
        body = {
            "username": username,
            "irods_path": irods_path,
        }
        if irods_user is not None:
            body["irods_user"] = irods_user
        r = httpx.post(
            self._url_join(["services", "register"]),
            json=body,
        )
        r.raise_for_status()
        return r.json()
