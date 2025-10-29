import functools
import os.path
import sys
import threading
import time
from urllib.parse import urljoin

import httpx
import jwt


class Formation(object):
    def __init__(
        self,
        api_url: str,
        keycloak_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
    ):
        self.base_url = f"{api_url}/" if not api_url.endswith("/") else api_url
        self.keycloak_url = keycloak_url.rstrip("/")
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret

        # Token state
        self._token = None
        self._token_expiry = 0
        self._lock = threading.Lock()
        self._refresh_buffer = 60  # Refresh 60s before expiry

    def api_url(self, *parts: str):
        part_path = functools.reduce(os.path.join, parts, "/").removeprefix("/")
        return urljoin(self.base_url, part_path)

    def _get_token_endpoint(self) -> str:
        """Build Keycloak token endpoint URL."""
        return f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"

    def _refresh_token(self):
        """Fetch new token from Keycloak using client credentials flow."""
        try:
            response = httpx.post(
                self._get_token_endpoint(),
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )
            response.raise_for_status()

            token_data = response.json()
            self._token = token_data["access_token"]

            # Decode JWT to get exact expiration
            self._token_expiry = self._decode_token_expiry(self._token)

            expires_in = token_data.get("expires_in", "unknown")
            print(
                f"[Formation] Token refreshed, expires in {expires_in}s",
                file=sys.stderr,
            )

        except Exception as e:
            print(f"[Formation] Token refresh failed: {e}", file=sys.stderr)
            raise

    def _decode_token_expiry(self, token: str) -> float:
        """Extract expiration timestamp from JWT without verification."""
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload.get("exp", 0)
        except Exception as e:
            print(f"[Formation] Failed to decode JWT: {e}", file=sys.stderr)
            return 0

    def _ensure_valid_token(self):
        """Ensure token is valid, refresh if needed."""
        current_time = time.time()

        # Fast path: token is still valid
        if self._token and current_time < self._token_expiry - self._refresh_buffer:
            return

        # Slow path: need to refresh
        with self._lock:
            # Double-check inside lock
            if current_time >= self._token_expiry - self._refresh_buffer:
                self._refresh_token()

    def get_app_parameters(self, system_id: str, app_id: str):
        """Get the parameters for an app.

        Args:
            system_id: The system ID (e.g., "de")
            app_id: The UUID of the app

        Returns:
            dict: The app parameters response containing groups and parameters
        """
        self._ensure_valid_token()
        r = httpx.get(
            self.api_url("apps", system_id, app_id, "parameters"),
            headers={"Authorization": f"Bearer {self._token}"},
        )
        r.raise_for_status()
        return r.json()

    def launch_analysis(
        self, system_id: str, app_id: str, submission: dict[str, any]
    ):
        """Launch an analysis.

        Args:
            system_id: The system ID (e.g., "de")
            app_id: The UUID of the app to launch
            submission: The analysis submission payload containing name, config, etc.

        Returns:
            dict: The launch response containing analysis_id and status
        """
        self._ensure_valid_token()
        r = httpx.post(
            self.api_url("app", "launch", system_id, app_id),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            json=submission,
        )
        r.raise_for_status()
        return r.json()

    def get_analysis_status(self, analysis_id: str):
        """Get the status of an analysis.

        Args:
            analysis_id: The UUID of the analysis

        Returns:
            dict: The status response containing analysis_id, status, url_ready, etc.
        """
        self._ensure_valid_token()
        r = httpx.get(
            self.api_url("apps", "analyses", analysis_id, "status"),
            headers={"Authorization": f"Bearer {self._token}"},
        )
        r.raise_for_status()
        return r.json()
