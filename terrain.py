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
        auth_string = base64.b64encode(
            f"{self.username}:{self.password}".encode("utf-8")
        ).decode("utf-8")
        auth_string = f"Basic {auth_string}"
        u = self.api_url("token", "keycloak")
        print(f"Requesting Keycloak token from: {u}")
        r = httpx.get(
            u,
            headers={"Authorization": auth_string},
        )
        r.raise_for_status()
        return r.json()["access_token"]

    def get_concurrent_job_limits(self, token: str, username: str):
        r = httpx.get(
            self.api_url("admin", "settings", "concurrent-job-limits", username),
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()

    def set_concurrent_job_limits(self, token: str, username: str, limit: int):
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

    def bootstrap_user(self, username: str, password: str):
        """Bootstrap a specific user in the Discovery Environment"""
        # Create a temporary Terrain client with the user's credentials
        user_terrain = Terrain(self.base_url, username, password)

        # Get a token for this specific user
        user_token = user_terrain.get_keycloak_token()

        # Call bootstrap with the user's token
        return user_terrain.bootstrap(user_token)
