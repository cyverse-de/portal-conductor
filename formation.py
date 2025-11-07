"""
Formation API client for interacting with the Formation service.

This module provides a thread-safe client for the Formation batch job service,
handling OAuth2 authentication via Keycloak and providing methods to launch
and monitor batch analyses.
"""

import functools
import os.path
import sys
import threading
import time
from urllib.parse import urljoin

import httpx
import jwt


class Formation:
    """
    Formation API client with automatic OAuth2 token management.

    This client handles authentication with Formation via Keycloak OAuth2,
    automatically refreshing tokens as needed. All token operations are
    thread-safe using double-check locking.

    Attributes:
        base_url: Formation API base URL.
        keycloak_url: Keycloak authentication server URL.
        realm: Keycloak realm name.
        client_id: OAuth2 client ID.
        client_secret: OAuth2 client secret.

    Example:
        ```python
        formation = Formation(
            api_url="http://formation:8080",
            keycloak_url="https://keycloak.example.com",
            realm="CyVerse",
            client_id="portal-conductor",
            client_secret="secret"
        )

        # Launch a job
        result = formation.launch_analysis(
            system_id="de",
            app_id="abc-123",
            submission={"name": "test-job", "config": {}}
        )

        # Check status
        status = formation.get_analysis_status(result["analysis_id"])
        ```
    """
    def __init__(
        self,
        api_url: str,
        keycloak_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        verify_ssl: bool = True,
    ):
        self.base_url = f"{api_url}/" if not api_url.endswith("/") else api_url
        self.keycloak_url = keycloak_url.rstrip("/")
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.verify_ssl = verify_ssl

        # Token state
        self._token = None
        self._token_expiry = 0
        self._lock = threading.Lock()
        self._refresh_buffer = 60  # Refresh 60s before expiry

    def api_url(self, *parts: str):
        part_path = functools.reduce(os.path.join, parts, "/").removeprefix("/")
        return urljoin(self.base_url, part_path)

    def _get_token_endpoint(self) -> str:
        """
        Build Keycloak token endpoint URL.

        Returns:
            str: The complete token endpoint URL.
        """
        return (
            f"{self.keycloak_url}/realms/{self.realm}/"
            f"protocol/openid-connect/token"
        )

    def _refresh_token(self) -> None:
        """
        Fetch new token from Keycloak using client credentials flow.

        Raises:
            httpx.HTTPStatusError: If token refresh fails.
        """
        response = httpx.post(
            self._get_token_endpoint(),
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
            verify=self.verify_ssl,
        )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Add response body to error message for debugging
            try:
                error_detail = response.json()
                raise httpx.HTTPStatusError(
                    f"{e.response.status_code} {e.response.reason_phrase}: {error_detail}",
                    request=e.request,
                    response=e.response,
                ) from e
            except Exception:
                # If we can't parse JSON, just raise the original error
                raise

        token_data = response.json()
        self._token = token_data["access_token"]

        # Decode JWT to get exact expiration
        self._token_expiry = self._decode_token_expiry(self._token)

        expires_in = token_data.get("expires_in", "unknown")
        print(
            f"[Formation] Token refreshed, expires in {expires_in}s",
            file=sys.stderr,
        )

    def _decode_token_expiry(self, token: str) -> float:
        """
        Extract expiration timestamp from JWT without verification.

        Args:
            token: JWT token string.

        Returns:
            float: Expiration timestamp, or 0 if decoding fails.
        """
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload.get("exp", 0)
        except Exception as e:
            print(
                f"[Formation] Failed to decode JWT: {e}",
                file=sys.stderr
            )
            return 0

    def _ensure_valid_token(self) -> None:
        """
        Ensure token is valid, refresh if needed.

        Thread-safe token validation and refresh with double-check locking.
        """
        current_time = time.time()

        # Fast path: token is still valid
        if self._token and current_time < self._token_expiry - self._refresh_buffer:
            return

        # Slow path: need to refresh
        with self._lock:
            # Double-check inside lock
            if current_time >= self._token_expiry - self._refresh_buffer:
                self._refresh_token()

    def search_apps(self, system_id: str, search: str):
        """
        Search for apps by name in Formation.

        Args:
            system_id: The system ID (e.g., "de").
            search: The search string (app name or partial name).

        Returns:
            dict: Search response with structure:
                ```python
                {
                    "apps": [
                        {
                            "id": "abc-123-def-456",
                            "name": "portal-delete-user",
                            ...
                        }
                    ]
                }
                ```

        Raises:
            httpx.HTTPStatusError: If the API request fails.
        """
        self._ensure_valid_token()
        r = httpx.get(
            self.api_url("apps"),
            params={"name": search},
            headers={"Authorization": f"Bearer {self._token}"},
            verify=self.verify_ssl,
        )
        r.raise_for_status()
        result = r.json()

        # Filter by system_id on the client side
        if "apps" in result:
            result["apps"] = [
                app for app in result["apps"]
                if app.get("system_id") == system_id
            ]
            result["total"] = len(result["apps"])

        return result

    def get_app_id_by_name(self, system_id: str, app_name: str):
        """
        Look up an app ID by its name.

        Searches for an app by name and returns its UUID. First tries an
        exact match, then falls back to case-insensitive matching.

        Args:
            system_id: The system ID (e.g., "de").
            app_name: The exact name of the app.

        Returns:
            str: The app ID (UUID) if found, None if not found.

        Example:
            ```python
            app_id = formation.get_app_id_by_name("de", "portal-delete-user")
            # Returns: "abc-123-def-456" or None
            ```

        Raises:
            httpx.HTTPStatusError: If the search API request fails.
        """
        results = self.search_apps(system_id, app_name)
        apps = results.get("apps", [])

        # Look for exact match first
        for app in apps:
            if app.get("name") == app_name:
                return app.get("id")

        # If no exact match, try case-insensitive
        app_name_lower = app_name.lower()
        for app in apps:
            if app.get("name", "").lower() == app_name_lower:
                return app.get("id")

        return None

    def get_app_parameters(self, system_id: str, app_id: str):
        """
        Get the parameters configuration for an app.

        Retrieves the app's parameter definitions including parameter groups,
        individual parameters, and their IDs. Used to build job submission
        payloads.

        Args:
            system_id: The system ID (e.g., "de").
            app_id: The UUID of the app.

        Returns:
            dict: App parameters with structure:
                ```python
                {
                    "groups": [
                        {
                            "parameters": [
                                {"id": "param-id", "name": "username", ...}
                            ]
                        }
                    ]
                }
                ```

        Raises:
            httpx.HTTPStatusError: If the API request fails.
        """
        self._ensure_valid_token()
        r = httpx.get(
            self.api_url("apps", system_id, app_id, "parameters"),
            headers={"Authorization": f"Bearer {self._token}"},
            verify=self.verify_ssl,
        )
        r.raise_for_status()
        return r.json()

    def launch_analysis(
        self, system_id: str, app_id: str, submission: dict[str, any]
    ):
        """
        Launch a batch analysis job.

        Submits a job to Formation for execution. The job is queued and
        executed asynchronously.

        Args:
            system_id: The system ID (e.g., "de").
            app_id: The UUID of the app to launch.
            submission: Job submission payload with structure:
                ```python
                {
                    "name": "job-name",
                    "config": {
                        "param-id-1": "value1",
                        "param-id-2": "value2"
                    }
                }
                ```

        Returns:
            dict: Launch response with structure:
                ```python
                {
                    "analysis_id": "abc-123-def-456",
                    "status": "Submitted"
                }
                ```

        Raises:
            httpx.HTTPStatusError: If the API request fails.

        Example:
            ```python
            result = formation.launch_analysis(
                system_id="de",
                app_id="abc-123",
                submission={
                    "name": "user-deletion-john.doe-1234567890",
                    "config": {"username-param-id": "john.doe"}
                }
            )
            # Returns: {"analysis_id": "xyz-789", "status": "Submitted"}
            ```
        """
        self._ensure_valid_token()
        r = httpx.post(
            self.api_url("app", "launch", system_id, app_id),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            json=submission,
            verify=self.verify_ssl,
        )
        r.raise_for_status()
        return r.json()

    def get_analysis_status(self, analysis_id: str):
        """
        Get the current status of a running or completed analysis.

        Queries Formation for the current state of a job. Use this to poll
        for job completion.

        Args:
            analysis_id: The UUID of the analysis (from launch_analysis).

        Returns:
            dict: Status response containing current job state and metadata.

        Raises:
            httpx.HTTPStatusError: If the API request fails or analysis not found.

        Example:
            ```python
            status = formation.get_analysis_status("abc-123-def-456")
            # Returns: {"analysis_id": "...", "status": "Running", ...}
            ```
        """
        self._ensure_valid_token()
        r = httpx.get(
            self.api_url("apps", "analyses", analysis_id, "status"),
            headers={"Authorization": f"Bearer {self._token}"},
            verify=self.verify_ssl,
        )
        r.raise_for_status()
        return r.json()
