#!/usr/bin/env python3
"""
Delete a user account from all CyVerse systems.

This script performs complete user deletion including:
- Portal database (user records, emails, workshop enrollments, form submissions, etc.)
- Mailing lists (removes user from all subscribed lists)
- iRODS datastore (home directory and user account)
- LDAP (user account and group memberships)

This script replicates the logic from the portal2 UI DELETE user workflow
but runs as a standalone CLI tool without web server overhead. It can run
for an indefinite amount of time for long-running deletion operations.

Usage:
    python scripts/delete-user.py username [--config path/to/config.json] [--dry-run]

Configuration:
    The script requires configuration for:
    - LDAP (user directory)
    - iRODS (data storage)
    - Portal Database (PostgreSQL)
    - Mailman (optional - for mailing list removal)

    Configuration can be provided via:
    1. JSON file specified with --config
    2. PORTAL_CONDUCTOR_CONFIG environment variable pointing to JSON file
    3. Individual environment variables (see config.json for structure)

    See delete-user.example.json for a complete configuration template.

Examples:
    # Delete user with default config
    python scripts/delete-user.py testuser

    # Use custom config file
    python scripts/delete-user.py testuser --config /etc/portal-conductor/delete-user-config.json

    # Preview what would be deleted (dry run)
    python scripts/delete-user.py testuser --dry-run

Exit Codes:
    0 - Success
    1 - Configuration error
    2 - User not found (reserved for future use)
    3 - Deletion error
"""

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

# Add project root to path for importing project modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import project modules
try:
    import portal_ldap
    import portal_datastore
    import mailman
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError as e:
    print(f"Error importing modules: {e}", file=sys.stderr)
    print("Make sure dependencies are installed (run 'uv sync')", file=sys.stderr)
    sys.exit(1)

# Exit codes
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_USER_NOT_FOUND = 2
EXIT_DELETION_ERROR = 3


def load_config(config_path):
    """Load configuration from JSON file or environment variables as fallback.

    Args:
        config_path: Path to JSON configuration file

    Returns:
        dict: Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist and env vars not set
        json.JSONDecodeError: If config file is invalid JSON
    """
    # Try to load from JSON file first
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                print(f"Loaded configuration from {config_path}", file=sys.stderr)
                return config
        except Exception as e:
            print(f"Failed to load config from {config_path}: {e}", file=sys.stderr)
            print("Falling back to environment variables", file=sys.stderr)

    # Fallback to environment variables
    config = {
        "ldap": {
            "url": os.environ.get("LDAP_URL", ""),
            "user": os.environ.get("LDAP_USER", ""),
            "password": os.environ.get("LDAP_PASSWORD", ""),
            "base_dn": os.environ.get("LDAP_BASE_DN", ""),
        },
        "irods": {
            "host": os.environ.get("IRODS_HOST", ""),
            "port": os.environ.get("IRODS_PORT", ""),
            "user": os.environ.get("IRODS_USER", ""),
            "password": os.environ.get("IRODS_PASSWORD", ""),
            "zone": os.environ.get("IRODS_ZONE", ""),
        },
        "portal_db": {
            "host": os.environ.get("PORTAL_DB_HOST", ""),
            "port": os.environ.get("PORTAL_DB_PORT", "5432"),
            "name": os.environ.get("PORTAL_DB_NAME", ""),
            "user": os.environ.get("PORTAL_DB_USER", ""),
            "password": os.environ.get("PORTAL_DB_PASSWORD", ""),
        },
        "mailman": {
            "enabled": os.environ.get("MAILMAN_ENABLED", "false").lower() == "true",
            "url": os.environ.get("MAILMAN_URL", ""),
            "password": os.environ.get("MAILMAN_PASSWORD", ""),
        }
    }

    return config


def validate_config(config):
    """Validate that all required configuration values are present.

    Args:
        config: Configuration dictionary

    Raises:
        ValueError: If required configuration fields are missing
    """
    required_fields = [
        ("ldap.url", config.get("ldap", {}).get("url")),
        ("ldap.user", config.get("ldap", {}).get("user")),
        ("ldap.password", config.get("ldap", {}).get("password")),
        ("ldap.base_dn", config.get("ldap", {}).get("base_dn")),
        ("irods.host", config.get("irods", {}).get("host")),
        ("irods.port", config.get("irods", {}).get("port")),
        ("irods.user", config.get("irods", {}).get("user")),
        ("irods.password", config.get("irods", {}).get("password")),
        ("irods.zone", config.get("irods", {}).get("zone")),
        ("portal_db.host", config.get("portal_db", {}).get("host")),
        ("portal_db.port", config.get("portal_db", {}).get("port")),
        ("portal_db.name", config.get("portal_db", {}).get("name")),
        ("portal_db.user", config.get("portal_db", {}).get("user")),
        ("portal_db.password", config.get("portal_db", {}).get("password")),
    ]

    missing_fields = [field_name for field_name, field_value in required_fields if not field_value]

    if missing_fields:
        raise ValueError(f"Missing required configuration fields: {', '.join(missing_fields)}")


def get_user_from_database(db_config, username):
    """Query portal database for user information.

    Args:
        db_config: Database configuration dictionary
        username: Username to query

    Returns:
        dict: User information including id, emails, and mailing lists
        None: If user not found

    Raises:
        Exception: If database query fails
    """
    try:
        conn = psycopg2.connect(
            host=db_config["host"],
            port=db_config["port"],
            dbname=db_config["name"],
            user=db_config["user"],
            password=db_config["password"]
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Query for user and their emails with mailing lists
        query = """
            SELECT
                u.id,
                u.username,
                u.email as primary_email,
                json_agg(
                    json_build_object(
                        'email', e.email,
                        'mailing_lists', (
                            SELECT json_agg(
                                json_build_object(
                                    'list_name', ml.list_name,
                                    'is_subscribed', eml.is_subscribed
                                )
                            )
                            FROM api_emailaddressmailinglist eml
                            JOIN api_mailinglist ml ON ml.id = eml.mailing_list_id
                            WHERE eml.email_address_id = e.id
                        )
                    )
                ) FILTER (WHERE e.id IS NOT NULL) as emails
            FROM account_user u
            LEFT JOIN account_emailaddress e ON e.user_id = u.id
            WHERE LOWER(u.username) = LOWER(%s)
            GROUP BY u.id, u.username, u.email
        """

        cursor.execute(query, (username,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if result:
            return dict(result)
        return None

    except Exception as e:
        print(f"Database query failed: {e}", file=sys.stderr)
        raise


def delete_user_from_mailing_lists(email_api, user_emails, dry_run=False):
    """Remove user from all mailing lists.

    Args:
        email_api: Email API instance
        user_emails: List of email dictionaries with mailing list information
        dry_run: If True, show what would be deleted without deleting
    """
    prefix = "[DRY RUN] " if dry_run else ""

    if not user_emails:
        print(f"{prefix}No email addresses found for user", file=sys.stderr)
        return

    for email_obj in user_emails:
        if not email_obj or not email_obj.get('mailing_lists'):
            continue

        email_addr = email_obj.get('email')
        mailing_lists = email_obj.get('mailing_lists', [])

        for ml in mailing_lists:
            if not ml:
                continue

            list_name = ml.get('list_name')
            if not list_name:
                continue

            try:
                print(f"{prefix}Removing {email_addr} from mailing list {list_name}", file=sys.stderr)
                if not dry_run:
                    email_api.remove_member(list_name, email_addr)
                print(f"{prefix}Removed {email_addr} from mailing list {list_name}", file=sys.stderr)
            except Exception as e:
                # Log but don't fail the entire deletion if mailing list removal fails
                print(f"{prefix}Failed to remove {email_addr} from mailing list {list_name}: {e}", file=sys.stderr)


def delete_user_from_portal_database(db_config, user_id, dry_run=False):
    """Delete user from portal database.

    Args:
        db_config: Database configuration dictionary
        user_id: User ID to delete
        dry_run: If True, show what would be deleted without deleting

    Raises:
        Exception: If database deletion fails
    """
    prefix = "[DRY RUN] " if dry_run else ""

    try:
        conn = psycopg2.connect(
            host=db_config["host"],
            port=db_config["port"],
            dbname=db_config["name"],
            user=db_config["user"],
            password=db_config["password"]
        )
        conn.autocommit = False
        cursor = conn.cursor()

        print(f"{prefix}Deleting user ID {user_id} from portal database", file=sys.stderr)

        # Delete in proper order to handle foreign key constraints
        # Legacy tables (from v1, no longer used)
        legacy_tables = [
            'django_cyverse_auth_token',
            'django_admin_log',
            'warden_atmosphereinternationalrequest',
            'warden_atmospherestudentrequest',
        ]

        for table in legacy_tables:
            print(f"{prefix}Deleting from {table}", file=sys.stderr)
            if not dry_run:
                cursor.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))

        # Handle FK constraints: Delete logs before their parent records
        print(f"{prefix}Deleting enrollment request logs", file=sys.stderr)
        if not dry_run:
            cursor.execute("""
                DELETE FROM api_workshopenrollmentrequestlog
                WHERE workshop_enrollment_request_id IN (
                    SELECT id FROM api_workshopenrollmentrequest WHERE user_id = %s
                )
            """, (user_id,))

        print(f"{prefix}Deleting access request logs", file=sys.stderr)
        if not dry_run:
            cursor.execute("""
                DELETE FROM api_accessrequestlog
                WHERE access_request_id IN (
                    SELECT id FROM api_accessrequest WHERE user_id = %s
                )
            """, (user_id,))

        # Core tables
        core_tables = [
            'account_passwordreset',
            'account_passwordresetrequest',
            'api_userservice',
            'api_formsubmission',
            'api_workshopenrollmentrequest',
            'api_accessrequest',
        ]

        for table in core_tables:
            print(f"{prefix}Deleting from {table}", file=sys.stderr)
            if not dry_run:
                cursor.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))

        # Delete workshop organizer records (uses organizer_id instead of user_id)
        print(f"{prefix}Deleting from api_workshoporganizer", file=sys.stderr)
        if not dry_run:
            cursor.execute("DELETE FROM api_workshoporganizer WHERE organizer_id = %s", (user_id,))

        # Delete email address mailing list associations before email addresses
        print(f"{prefix}Deleting from api_emailaddressmailinglist", file=sys.stderr)
        if not dry_run:
            cursor.execute("""
                DELETE FROM api_emailaddressmailinglist
                WHERE email_address_id IN (
                    SELECT id FROM account_emailaddress WHERE user_id = %s
                )
            """, (user_id,))

        # Delete email addresses (must be before user deletion due to FK constraint)
        print(f"{prefix}Deleting from account_emailaddress", file=sys.stderr)
        if not dry_run:
            cursor.execute("DELETE FROM account_emailaddress WHERE user_id = %s", (user_id,))

        # Finally, delete the user
        print(f"{prefix}Deleting user record from account_user", file=sys.stderr)
        if not dry_run:
            cursor.execute("DELETE FROM account_user WHERE id = %s", (user_id,))
            conn.commit()
            print(f"{prefix}Database deletion committed", file=sys.stderr)
        else:
            print(f"{prefix}Would delete user record (dry run, no commit)", file=sys.stderr)

        cursor.close()
        conn.close()

    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        print(f"Database deletion failed: {e}", file=sys.stderr)
        raise


def delete_user_from_datastore(ds_api, username, dry_run=False):
    """Delete user's home directory and account from datastore.

    Args:
        ds_api: DataStore API instance
        username: Username to delete
        dry_run: If True, show what would be deleted without deleting
    """
    prefix = "[DRY RUN] " if dry_run else ""

    print(f"{prefix}Checking if user exists in datastore: {username}", file=sys.stderr)
    if ds_api.user_exists(username):
        print(f"{prefix}Deleting home directory for user: {username}", file=sys.stderr)
        if not dry_run:
            ds_api.delete_home(username)
        print(f"{prefix}Deleted home directory for user: {username}", file=sys.stderr)

        print(f"{prefix}Deleting datastore user: {username}", file=sys.stderr)
        if not dry_run:
            ds_api.delete_user(username)
        print(f"{prefix}Deleted datastore user: {username}", file=sys.stderr)
    else:
        print(f"{prefix}User {username} does not exist in datastore, skipping datastore deletion", file=sys.stderr)


def delete_user_from_ldap(ldap_conn, ldap_base_dn, username, dry_run=False):
    """Remove user from all LDAP groups and delete account.

    Args:
        ldap_conn: LDAP connection object
        ldap_base_dn: LDAP base DN
        username: Username to delete
        dry_run: If True, show what would be deleted without deleting
    """
    prefix = "[DRY RUN] " if dry_run else ""

    print(f"{prefix}Checking if user {username} exists in LDAP", file=sys.stderr)
    existing_user = portal_ldap.get_user(ldap_conn, ldap_base_dn, username)

    if existing_user and len(existing_user) > 0:
        # Remove from LDAP groups
        print(f"{prefix}Getting LDAP groups for user: {username}", file=sys.stderr)
        user_groups = portal_ldap.get_user_groups(ldap_conn, ldap_base_dn, username)
        print(f"{prefix}User {username} is in {len(user_groups)} groups", file=sys.stderr)

        for ug in user_groups:
            group_name = ug[1]["cn"][0].decode('utf-8') if isinstance(ug[1]["cn"][0], bytes) else ug[1]["cn"][0]
            print(f"{prefix}Removing user {username} from group {group_name}", file=sys.stderr)
            if not dry_run:
                portal_ldap.remove_user_from_group(ldap_conn, ldap_base_dn, username, group_name)
            print(f"{prefix}Removed user {username} from group {group_name}", file=sys.stderr)

        # Delete from LDAP
        print(f"{prefix}Deleting user {username} from LDAP", file=sys.stderr)
        if not dry_run:
            portal_ldap.delete_user(ldap_conn, ldap_base_dn, username)
        print(f"{prefix}Deleted LDAP user: {username}", file=sys.stderr)
    else:
        print(f"{prefix}User {username} does not exist in LDAP, skipping LDAP deletion", file=sys.stderr)


def delete_user(config, ldap_conn, ldap_base_dn, ds_api, email_api, username, dry_run=False):
    """Delete a user account from all systems.

    This function orchestrates the complete user deletion process:
    1. Query portal database for user information
    2. Remove from mailing lists (if mailman enabled)
    3. Delete from datastore (home directory and user account)
    4. Delete from LDAP (remove from groups and delete user)
    5. Delete from portal database

    Args:
        config: Configuration dictionary
        ldap_conn: LDAP connection object
        ldap_base_dn: LDAP base DN
        ds_api: DataStore API instance
        email_api: Email API instance (or None if mailman disabled)
        username: Username to delete
        dry_run: If True, show what would be deleted without deleting

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        prefix = "[DRY RUN] " if dry_run else ""
        print(f"{prefix}Starting deletion for user: {username}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        # Get user information from portal database
        print(f"{prefix}Phase 0: Querying portal database", file=sys.stderr)
        user_info = get_user_from_database(config["portal_db"], username)
        if not user_info:
            print(f"User {username} not found in portal database", file=sys.stderr)
            return False

        user_id = user_info['id']
        user_emails = user_info.get('emails', [])
        print(f"{prefix}Found user ID {user_id} with {len(user_emails) if user_emails else 0} email address(es)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        # Remove from mailing lists
        if email_api and user_emails:
            print(f"{prefix}Phase 1: Mailing list removal", file=sys.stderr)
            delete_user_from_mailing_lists(email_api, user_emails, dry_run)
            print("=" * 60, file=sys.stderr)
        else:
            print(f"{prefix}Phase 1: Skipping mailing list removal (mailman not enabled or no emails)", file=sys.stderr)
            print("=" * 60, file=sys.stderr)

        # Delete from datastore
        print(f"{prefix}Phase 2: Datastore deletion", file=sys.stderr)
        delete_user_from_datastore(ds_api, username, dry_run)
        print("=" * 60, file=sys.stderr)

        # Delete from LDAP
        print(f"{prefix}Phase 3: LDAP deletion", file=sys.stderr)
        delete_user_from_ldap(ldap_conn, ldap_base_dn, username, dry_run)
        print("=" * 60, file=sys.stderr)

        # Delete from portal database
        print(f"{prefix}Phase 4: Portal database deletion", file=sys.stderr)
        delete_user_from_portal_database(config["portal_db"], user_id, dry_run)
        print("=" * 60, file=sys.stderr)

        print(f"{prefix}User deletion completed successfully: {username}", file=sys.stderr)
        return True

    except Exception as e:
        print("=" * 60, file=sys.stderr)
        print(f"User deletion failed for {username}: {str(e)}", file=sys.stderr)
        print(f"Exception type: {type(e).__name__}", file=sys.stderr)
        print(f"Traceback:\n{traceback.format_exc()}", file=sys.stderr)
        return False


def main():
    """Main script entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Delete a user from LDAP, iRODS datastore, mailing lists, and portal database',
        epilog='Example: python scripts/delete-user.py testuser --dry-run',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('username', help='Username to delete')
    parser.add_argument(
        '--config',
        help='Path to config file (default: PORTAL_CONDUCTOR_CONFIG env var or config.json)',
        default=os.environ.get('PORTAL_CONDUCTOR_CONFIG', 'config.json')
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without actually deleting'
    )
    args = parser.parse_args()

    # Load and validate configuration
    try:
        config = load_config(args.config)
        validate_config(config)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("\nMake sure you have a valid config.json or set environment variables:", file=sys.stderr)
        print("  LDAP_URL, LDAP_USER, LDAP_PASSWORD, LDAP_BASE_DN", file=sys.stderr)
        print("  IRODS_HOST, IRODS_PORT, IRODS_USER, IRODS_PASSWORD, IRODS_ZONE", file=sys.stderr)
        print("  PORTAL_DB_HOST, PORTAL_DB_PORT, PORTAL_DB_NAME, PORTAL_DB_USER, PORTAL_DB_PASSWORD", file=sys.stderr)
        print("  MAILMAN_ENABLED, MAILMAN_URL, MAILMAN_PASSWORD (optional)", file=sys.stderr)
        sys.exit(EXIT_CONFIG_ERROR)

    # Initialize connections
    print("Initializing connections...", file=sys.stderr)
    try:
        ldap_conn = portal_ldap.connect(
            config["ldap"]["url"],
            config["ldap"]["user"],
            config["ldap"]["password"]
        )
        print(f"Connected to LDAP: {config['ldap']['url']}", file=sys.stderr)

        ds_api = portal_datastore.DataStore(
            config["irods"]["host"],
            config["irods"]["port"],
            config["irods"]["user"],
            config["irods"]["password"],
            config["irods"]["zone"]
        )
        print(f"Connected to iRODS: {config['irods']['host']}", file=sys.stderr)

        # Initialize email API if mailman is enabled
        email_api = None
        if config.get("mailman", {}).get("enabled", False):
            try:
                email_api = mailman.Mailman(
                    api_url=config["mailman"]["url"],
                    password=config["mailman"]["password"]
                )
                print(f"Connected to Mailman: {config['mailman']['url']}", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Failed to initialize Mailman connection: {e}", file=sys.stderr)
                print("Mailing list removal will be skipped", file=sys.stderr)
        else:
            print("Mailman not enabled, mailing list removal will be skipped", file=sys.stderr)

        print("=" * 60, file=sys.stderr)
    except Exception as e:
        print(f"Failed to initialize connections: {e}", file=sys.stderr)
        print(f"Traceback:\n{traceback.format_exc()}", file=sys.stderr)
        sys.exit(EXIT_CONFIG_ERROR)

    # Perform deletion
    success = delete_user(
        config,
        ldap_conn,
        config["ldap"]["base_dn"],
        ds_api,
        email_api,
        args.username,
        dry_run=args.dry_run
    )

    # Exit with appropriate code
    if success:
        if args.dry_run:
            print(f"\nDry run completed for user: {args.username}", file=sys.stderr)
            print("No changes were made. Run without --dry-run to perform actual deletion.", file=sys.stderr)
        else:
            print(f"\nSuccessfully deleted user: {args.username}", file=sys.stdout)
        sys.exit(EXIT_SUCCESS)
    else:
        print(f"\nFailed to delete user: {args.username}", file=sys.stderr)
        sys.exit(EXIT_DELETION_ERROR)


if __name__ == "__main__":
    main()
