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

    def _set_permission_if_needed(self, current_perms: list[iRODSAccess],
                                  username: str, permission: str, path: str) -> bool:
        """
        Helper method to set permission only if it doesn't already exist.

        Args:
            current_perms: List of current permissions for the path
            username: Username to set permission for (empty string for inherit)
            permission: Permission type to set
            path: Path to set permission on

        Returns:
            bool: True if permission was set, False if it already existed
        """
        perm_exists = any(
            perm.user_name == username and perm.access_name == permission
            for perm in current_perms
        )
        if not perm_exists:
            perm = PathPermission(username=username, permission=permission, path=path)
            self.chmod(perm)
            return True
        return False

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

        # Create directory if it doesn't exist
        if not self.path_exists(full_path):
            self.session.collections.create(full_path)

        # Set permissions idempotently
        current_perms = self.path_permissions(full_path)

        # Set inherit permission if not already set
        self._set_permission_if_needed(current_perms, "", "inherit", full_path)

        # Set owner permission for username if not already set
        self._set_permission_if_needed(current_perms, username, "own", full_path)

        # Set owner permission for irods_user if specified and not already set
        if irods_user is not None:
            self._set_permission_if_needed(current_perms, irods_user, "own", full_path)

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

    def create_datastore_user_with_permissions(self, username: str, password: str,
                                               ipcservices_user: str, ds_admin_user: str):
        """
        Create a datastore user with home directory and default permissions (idempotent).

        This function handles the complete datastore user creation workflow:
        - Creates the user account in iRODS (if it doesn't exist)
        - Sets the user's password (always set for security - not truly idempotent)
        - Creates the user's home directory (if it doesn't exist)
        - Sets appropriate permissions for ipcservices and admin users

        All operations except password setting are performed idempotently.
        Password is always updated for security reasons as iRODS doesn't provide
        a secure way to verify if the current password matches the desired password.

        Args:
            username: The username to create
            password: The password for the user
            ipcservices_user: Username for ipcservices permissions
            ds_admin_user: Username for admin permissions

        Returns:
            str: The username of the created/existing user

        Raises:
            Exception: If user creation, directory creation, or permission setting fails
        """
        # Health check before operations
        print(f"Creating data store user: {username}", file=sys.stderr)
        self.health_check()

        # Ensure user exists (create if necessary) - this is idempotent
        self.ensure_user_exists(username)

        # Set password - NOTE: This is not idempotent for security reasons
        # iRODS doesn't provide a secure way to check if password is already set
        print(f"Setting data store password for: {username}", file=sys.stderr)
        self.change_password(username, password)

        # Get home directory path
        print(f"Getting home directory for: {username}", file=sys.stderr)
        home_dir = self.user_home(username)

        # Set permissions idempotently
        current_perms = self.path_permissions(home_dir)

        # Set ipcservices permissions if not already set
        ipcservices_owns = any(
            perm.user_name == ipcservices_user and perm.access_name == "own"
            for perm in current_perms
        )
        if not ipcservices_owns:
            print(f"Setting ipcservices permissions for: {home_dir}", file=sys.stderr)
            ipcservices_perm = PathPermission(
                username=ipcservices_user,
                permission="own",
                path=home_dir,
            )
            self.chmod(ipcservices_perm)
        else:
            print(f"ipcservices user {ipcservices_user} already owns {home_dir}", file=sys.stderr)

        # Set admin permissions if not already set
        admin_owns = any(
            perm.user_name == ds_admin_user and perm.access_name == "own"
            for perm in current_perms
        )
        if not admin_owns:
            print(f"Setting rodsadmin permissions for: {home_dir}", file=sys.stderr)
            rodsadmin_perm = PathPermission(
                username=ds_admin_user,
                permission="own",
                path=home_dir,
            )
            self.chmod(rodsadmin_perm)
        else:
            print(f"Admin user {ds_admin_user} already owns {home_dir}", file=sys.stderr)

        return username
