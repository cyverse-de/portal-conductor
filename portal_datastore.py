import os.path
import sys

from irods.access import iRODSAccess
from irods.exception import UserDoesNotExist
from irods.path import iRODSPath
from irods.session import iRODSSession
from irods.user import iRODSUser
from pydantic import BaseModel


class PathPermission(BaseModel):
    username: str
    path: str
    permission: str


class DataStore(object):
    _user_type = "rodsuser"

    def __init__(self, host: str, port: str, user: str, password: str, zone: str):
        self.session = iRODSSession(
            host=host, port=port, user=user, password=password, zone=zone
        )
        self.session.connection_timeout = None
        self.host = host
        self.port = port
        self.user = user
        self.zone = zone

    def health_check(self) -> bool:
        """
        Check if the datastore service is reachable and healthy.

        Returns:
            bool: True if the service is healthy, False otherwise
        """
        try:
            print(f"Checking datastore service health at: {self.host}:{self.port}", file=sys.stderr)
            # Try a simple operation to check connectivity
            self.session.server_version
            print("Datastore health check: OK", file=sys.stderr)
            return True
        except Exception as health_error:
            print(f"Datastore health check failed: {type(health_error).__name__}: {health_error}", file=sys.stderr)
            return False

    def list_available_permissions(self) -> list[str]:
        return list(self.session.available_permissions.keys())

    def path_exists(self, path: str) -> bool:
        fixed_path = iRODSPath(path)
        return self.session.data_objects.exists(
            fixed_path
        ) or self.session.collections.exists(fixed_path)

    def path_permissions(self, path: str) -> list[iRODSAccess]:
        clean_path = iRODSPath(path)

        obj = None
        if self.session.data_objects.exists(clean_path):
            obj = self.session.data_objects.get(clean_path)
        else:
            obj = self.session.collections.get(clean_path)

        return self.session.acls.get(obj)

    def user_exists(self, username: str) -> bool:
        try:
            user = self.session.users.get(username, self.zone)
            return user is not None
        except UserDoesNotExist:
            return False

    def create_user(self, username: str) -> iRODSUser:
        try:
            return self.session.users.create(username, DataStore._user_type)
        except Exception as e:
            print(
                f"DataStore connection error for create_user('{username}'): {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            raise

    def user_home(self, username: str) -> str:
        try:
            return str(iRODSPath(f"/{self.zone}/home/{username}"))
        except Exception as e:
            print(
                f"DataStore connection error for user_home('{username}'): {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            raise

    def delete_user(self, username: str) -> None:
        self.session.users.get(username, self.zone).remove()

    def delete_home(self, username: str) -> None:
        homedir = self.user_home(username)
        if self.session.collections.exists(homedir):
            self.session.collections.remove(homedir, force=True, recurse=True)

    def change_password(self, username: str, new_password: str) -> None:
        try:
            self.session.users.modify(username, "password", new_password)
        except Exception as e:
            print(
                f"DataStore connection error for change_password('{username}'): {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            raise

    def chmod(self, perm: PathPermission) -> None:
        try:
            access = iRODSAccess(perm.permission, iRODSPath(perm.path), perm.username)
            self.session.acls.set(access)
        except Exception as e:
            print(
                f"DataStore connection error for chmod('{perm.path}'): {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            raise

    def register_service(
        self, username: str, irods_path: str, irods_user: str | None = None
    ):
        # Ensure user exists (create if necessary)
        try:
            self.ensure_user_exists(username)
            print(f"User {username} is ready for service registration", file=sys.stderr)
        except Exception as e:
            print(f"Failed to ensure user {username} exists: {str(e)}", file=sys.stderr)
            raise Exception(f"Failed to prepare user {username}: {str(e)}")

        home_dir = self.user_home(username)

        full_path = os.path.join(home_dir, irods_path)
        if not self.path_exists(full_path):
            self.session.collections.create(full_path)

        # Set permissions idempotently - check current permissions first
        current_perms = self.path_permissions(full_path)

        # Set inherit permission if not already set
        inherit_set = any(perm.user_name == "" and perm.access_name == "inherit" for perm in current_perms)
        if not inherit_set:
            inherit_perm = PathPermission(username="", permission="inherit", path=full_path)
            self.chmod(inherit_perm)

        # Set owner permission for username if not already set
        user_owns = any(perm.user_name == username and perm.access_name == "own" for perm in current_perms)
        if not user_owns:
            user_perm = PathPermission(username=username, permission="own", path=full_path)
            self.chmod(user_perm)

        # Set owner permission for irods_user if specified and not already set
        if irods_user is not None:
            irods_user_owns = any(perm.user_name == irods_user and perm.access_name == "own" for perm in current_perms)
            if not irods_user_owns:
                irods_user_perm = PathPermission(username=irods_user, permission="own", path=full_path)
                self.chmod(irods_user_perm)

        return {
            "user": username,
            "irods_path": full_path,
            "irods_user": irods_user,
        }

    def get_user(self, username: str) -> iRODSUser:
        return self.session.users.get(username, self.zone)

    def ensure_user_exists(self, username: str) -> iRODSUser:
        """
        Ensure a user exists in iRODS, creating them and their home directory if necessary.

        Args:
            username: The username to ensure exists

        Returns:
            iRODSUser: The user object (either existing or newly created)

        Raises:
            Exception: If user or home directory creation fails
        """
        # Check if user already exists
        if self.user_exists(username):
            return self.get_user(username)

        # Create the user
        user = self.create_user(username)

        # Ensure home directory exists
        home_dir = self.user_home(username)
        if not self.path_exists(home_dir):
            # Create home directory
            self.session.collections.create(home_dir)
            # Set ownership of home directory to the user
            home_perm = PathPermission(username=username, permission="own", path=home_dir)
            self.chmod(home_perm)

        return user
