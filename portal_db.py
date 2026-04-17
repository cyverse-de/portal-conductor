"""
Portal Database client for PostgreSQL operations.

Provides methods for querying and modifying user data in the portal database.
"""

import sys
from datetime import datetime, timezone
from typing import Any

from psycopg2 import pool


class PortalDB:
    """PostgreSQL client for portal database operations."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        min_connections: int = 1,
        max_connections: int = 10,
    ):
        """
        Initialize the portal database client.

        Args:
            host: PostgreSQL server hostname.
            port: PostgreSQL server port.
            database: Database name.
            user: Database username.
            password: Database password.
            min_connections: Minimum connections in pool.
            max_connections: Maximum connections in pool.
        """
        self.connection_pool = pool.ThreadedConnectionPool(
            minconn=min_connections,
            maxconn=max_connections,
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )
        print(
            f"Portal database connection pool initialized: {host}:{port}/{database}",
            file=sys.stderr,
        )

    def _get_connection(self):
        """Get a connection from the pool."""
        return self.connection_pool.getconn()

    def _return_connection(self, conn):
        """Return a connection to the pool."""
        self.connection_pool.putconn(conn)

    def health_check(self) -> bool:
        """
        Check database connectivity.

        Returns:
            True if database is accessible.
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as e:
            print(f"Portal database health check failed: {e}", file=sys.stderr)
            return False
        finally:
            if conn:
                self._return_connection(conn)

    def user_exists_by_username(self, username: str) -> bool:
        """
        Check if a user exists in the account_user table.

        Args:
            username: Username to check.

        Returns:
            True if user exists.
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM account_user WHERE username = %s LIMIT 1",
                    (username,),
                )
                return cur.fetchone() is not None
        finally:
            if conn:
                self._return_connection(conn)

    def is_restricted_username(self, username: str) -> bool:
        """
        Check if a username is in the restricted usernames list.

        Args:
            username: Username to check.

        Returns:
            True if username is restricted.
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM account_restrictedusername WHERE username = %s LIMIT 1",
                    (username,),
                )
                return cur.fetchone() is not None
        finally:
            if conn:
                self._return_connection(conn)

    def email_exists(self, email: str) -> bool:
        """
        Check if an email exists in the account_emailaddress table.

        Case-insensitive comparison.

        Args:
            email: Email address to check.

        Returns:
            True if email exists.
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM account_emailaddress WHERE LOWER(email) = LOWER(%s) LIMIT 1",
                    (email,),
                )
                return cur.fetchone() is not None
        finally:
            if conn:
                self._return_connection(conn)

    def create_user(self, user_data: dict[str, Any]) -> int:
        """
        Create a new user in the account_user table.

        Args:
            user_data: Dictionary containing user fields. Required fields:
                - username
                - email
                - password (hashed)
                - first_name
                - last_name
                - institution
                - department
                - occupation_id
                - funding_agency_id
                - gender_id
                - ethnicity_id
                - region_id
                - research_area_id
                - aware_channel_id

        Returns:
            The new user's ID.

        Raises:
            psycopg2.Error: If user creation fails.
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                now = datetime.now(timezone.utc)
                cur.execute(
                    """
                    INSERT INTO account_user (
                        username, email, password, first_name, last_name,
                        institution, department, occupation_id, funding_agency_id,
                        gender_id, ethnicity_id, region_id, research_area_id,
                        aware_channel_id, is_superuser, is_staff, is_active,
                        has_verified_email, participate_in_study, subscribe_to_newsletter,
                        orcid_id, date_joined, updated_at, grid_institution_id
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s
                    ) RETURNING id
                    """,
                    (
                        user_data["username"],
                        user_data["email"].lower(),
                        user_data.get("password", ""),
                        user_data["first_name"],
                        user_data["last_name"],
                        user_data["institution"],
                        user_data["department"],
                        user_data["occupation_id"],
                        user_data["funding_agency_id"],
                        user_data["gender_id"],
                        user_data["ethnicity_id"],
                        user_data["region_id"],
                        user_data["research_area_id"],
                        user_data["aware_channel_id"],
                        user_data.get("is_superuser", False),
                        user_data.get("is_staff", False),
                        user_data.get("is_active", True),
                        user_data.get("has_verified_email", False),
                        user_data.get("participate_in_study", True),
                        user_data.get("subscribe_to_newsletter", True),
                        user_data.get("orcid_id", ""),
                        now,
                        now,
                        user_data.get("grid_institution_id"),
                    ),
                )
                user_id = cur.fetchone()[0]
                conn.commit()
                print(f"Created portal user: {user_data['username']} (id={user_id})", file=sys.stderr)
                return user_id
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def create_email_address(
        self,
        user_id: int,
        email: str,
        primary: bool = True,
        verified: bool = False,
    ) -> int:
        """
        Create an email address entry for a user.

        Args:
            user_id: The user's ID.
            email: Email address.
            primary: Whether this is the primary email.
            verified: Whether the email is verified.

        Returns:
            The new email address ID.

        Raises:
            psycopg2.Error: If creation fails.
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                now = datetime.now(timezone.utc)
                cur.execute(
                    """
                    INSERT INTO account_emailaddress (
                        user_id, email, "primary", verified, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, email.lower(), primary, verified, now, now),
                )
                email_id = cur.fetchone()[0]
                conn.commit()
                print(f"Created email address for user {user_id}: {email}", file=sys.stderr)
                return email_id
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        """
        Get user data by username.

        Args:
            username: Username to look up.

        Returns:
            Dictionary with user data or None if not found.
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, username, email, first_name, last_name,
                           institution, department, occupation_id, is_active
                    FROM account_user
                    WHERE username = %s
                    """,
                    (username,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return {
                    "id": row[0],
                    "username": row[1],
                    "email": row[2],
                    "first_name": row[3],
                    "last_name": row[4],
                    "institution": row[5],
                    "department": row[6],
                    "occupation_id": row[7],
                    "is_active": row[8],
                }
        finally:
            if conn:
                self._return_connection(conn)

    def get_occupation_name(self, occupation_id: int) -> str | None:
        """
        Get occupation name by ID.

        Args:
            occupation_id: The occupation ID.

        Returns:
            Occupation name or None if not found.
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name FROM account_occupation WHERE id = %s",
                    (occupation_id,),
                )
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            if conn:
                self._return_connection(conn)

    def close(self):
        """Close all connections in the pool."""
        if self.connection_pool:
            self.connection_pool.closeall()
            print("Portal database connection pool closed", file=sys.stderr)
