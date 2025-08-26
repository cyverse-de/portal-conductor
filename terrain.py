import base64
import functools
import os.path
from urllib.parse import urljoin

import httpx


class Terrain(object):
    def __init__(self, api_url: str, username: str, password: str):
        self.base_url = f"{api_url}/" if not api_url.endswith("/") else api_url
        self.username = username
        self.password = password

    def api_url(self, *parts: str):
        part_path = functools.reduce(os.path.join, parts, "/").removeprefix("/")
        return urljoin(self.base_url, part_path)

    def get_keycloak_token(self):
        auth_string = f"Basic {self.username}:{self.password}"
        auth_string = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

        r = httpx.get(
            self.api_url("token", "keycloak"),
            headers={"Authorization": auth_string},
        )
        r.raise_for_status()
        return r.json()["access_token"]

    def set_concurrent_job_limits(self, token: str, username: str, limit: str):
        r = httpx.put(
            self.api_url("admin", "settings", "concurrent-job-limits", username),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"concurrent_jobs": limit},
        )
        r.raise_for_status()
        return r.json()

    def request_vice_access(
        self, token: str, first_name: str, last_name: str, email: str, usage: str
    ):
        r = httpx.post(
            self.api_url("requests", "vice"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "name": f"{first_name} {last_name}",
                "email": email,
                "intended_usage": usage,
                "concurrent_jobs": 2,
            },
        )
        r.raise_for_status()
        return r.json()

    def bootstrap(self, token: str):
        r = httpx.get(
            self.api_url("secured", "bootstrap"),
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()
