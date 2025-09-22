# portal_ldap
#
# Contains LDAP operations needed for the portal. Included here in a separate
# file to make them easier to use from an interactive session.

import ldap
import ldap.modlist
import kinds
import datetime
import sys


def connect(ldap_url, ldap_user, ldap_password):
    ldap.set_option(ldap.OPT_TIMEOUT, None)

    conn = ldap.ldapobject.ReconnectLDAPObject(
        ldap_url, retry_max=5, retry_delay=3.0
    )
    conn.set_option(ldap.OPT_REFERRALS, 0)
    conn.simple_bind_s(ldap_user, ldap_password)
    return conn


def get_user_dn(conn, base_dn, username: str):
    search_filter = f"(&(objectClass=person)(uid={username}))"
    result = conn.search_s(base_dn, ldap.SCOPE_SUBTREE, search_filter)
    retval = ""
    if result and result[0]:
        retval = result[0][0]
    return retval


default_group_attrlist = [
    "objectClass",
    "displayName",
    "sambaGroupType",
    "sambaSID",
    "gidNumber",
    "cn",
    "description",
]


def days_since_epoch():
    epoch = datetime.datetime.fromtimestamp(0, datetime.UTC)
    today = datetime.datetime.now(datetime.UTC)
    diff = today - epoch
    return diff.days


def validate_uid_number(user_uid: str) -> int:
    """Validate and convert uidNumber to ensure it's a valid positive integer."""
    try:
        uid_number = int(user_uid)
        if uid_number <= 0:
            raise ValueError(f"uidNumber must be a positive integer, got: {user_uid}")
        return uid_number
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid uidNumber '{user_uid}': must be a positive integer") from e


def validate_shadow_last_change(days_since_epoch) -> int:
    """Validate and convert shadowLastChange to ensure it's a valid non-negative integer."""
    try:
        shadow_last_change = int(days_since_epoch) if isinstance(days_since_epoch, str) else days_since_epoch
        if shadow_last_change < 0:
            raise ValueError(f"shadowLastChange must be non-negative, got: {shadow_last_change}")
        return shadow_last_change
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid shadowLastChange '{days_since_epoch}': must be a non-negative integer") from e


# Returns a list of tuples of the format: (dn, attribute map). The attribute map contains
# key-value pairs with the keys coming from the attrlist parameter. The attrlist
# parameter excludes the memberUid attribute because it's likely to be a huge list of
# usernames and retrieving them all is an expensive operation.
def get_user_groups(
    conn,
    base_dn,
    username: str,
    attrlist=default_group_attrlist,
):
    search_filter = f"(&(objectClass=posixGroup)(memberUid={username}))"
    result = conn.search_s(
        base_dn, ldap.SCOPE_SUBTREE, search_filter, attrlist=attrlist
    )
    return result


def get_groups(
    conn,
    base_dn,
    attrlist=default_group_attrlist,
):
    search_filter = "(&(objectClass=posixGroup))"
    return conn.search_s(
        base_dn, ldap.SCOPE_SUBTREE, search_filter, attrlist=attrlist
    )


def get_user(conn, base_dn, username: str):
    search_filter = f"(&(objectClass=posixAccount)(uid={username}))"
    return conn.search_s(base_dn, ldap.SCOPE_SUBTREE, search_filter)


list_user_attrs = ["uid", "uidNumber"]


def list_users(conn, base_dn: str, attrlist=list_user_attrs):
    search_filter = "(&(objectClass=posixAccount))"
    return conn.search_s(
        base_dn, ldap.SCOPE_SUBTREE, search_filter, attrlist=attrlist
    )


def create_user(conn, base_dn, days_since_epoch, user: kinds.CreateUserRequest):
    # Validate input parameters
    uid_number = validate_uid_number(user.user_uid)
    shadow_last_change = validate_shadow_last_change(days_since_epoch)

    new_user = ldap.modlist.addModlist(
        {
            "objectClass": [
                b"posixAccount",
                b"shadowAccount",
                b"inetOrgPerson",
            ],
            "givenName": user.first_name.encode("UTF-8"),
            "sn": user.last_name.encode("UTF-8"),
            "cn": f"{user.first_name} {user.last_name}".encode("UTF-8"),
            "uid": user.username.encode("UTF-8"),
            "userPassword": user.password.encode("UTF-8"),
            "mail": user.email.encode("UTF-8"),
            "departmentNumber": user.department.encode("UTF-8"),
            "o": user.organization.encode("UTF-8"),
            "title": user.title.encode("UTF-8"),
            "homeDirectory": f"/home/{user.username}".encode("UTF-8"),
            "loginShell": b"/bin/bash",
            "gidNumber": b"10013",
            "uidNumber": str(uid_number).encode("UTF-8"),
            "shadowLastChange": str(shadow_last_change).encode("UTF-8"),
            "shadowMin": b"1",
            "shadowMax": b"730",
            "shadowInactive": b"10",
            "shadowWarning": b"10",
        }
    )
    return conn.add_s(f"uid={user.username},ou=People,{base_dn}", new_user)


def create_ldap_user_with_groups(conn, base_dn, user: kinds.CreateUserRequest,
                                 everyone_group: str | None = None,
                                 community_group: str | None = None):
    """
    Create a user in LDAP and optionally add them to default groups (idempotent).

    This function handles the complete LDAP user creation workflow:
    - Creates the user account in LDAP (if it doesn't exist)
    - Sets the user's password
    - Adds the user to specified groups (if provided and not already a member)

    All operations are performed idempotently - existing resources are left unchanged.

    Args:
        conn: LDAP connection object
        base_dn: LDAP base distinguished name
        user: User information including personal details and credentials
        everyone_group: Optional name of the "everyone" group to add user to
        community_group: Optional name of the "community" group to add user to

    Returns:
        str: The username of the created/existing user

    Raises:
        Exception: If user creation or group addition fails
    """
    # Check if user already exists
    existing_user = get_user(conn, base_dn, user.username)
    if not existing_user or len(existing_user) == 0:
        dse = days_since_epoch()
        print(f"Creating LDAP user: {user.username}", file=sys.stderr)
        create_user(conn, base_dn, dse, user)

        print(f"Setting LDAP password for: {user.username}", file=sys.stderr)
        change_password(conn, base_dn, user.username, user.password)
    else:
        print(f"LDAP user {user.username} already exists, skipping creation", file=sys.stderr)

    # Add to groups if specified and not already a member
    if everyone_group:
        user_groups = [g[1]["cn"][0].decode('utf-8') for g in get_user_groups(conn, base_dn, user.username)]
        if everyone_group not in user_groups:
            print(f"Adding user {user.username} to everyone group: {everyone_group}", file=sys.stderr)
            add_user_to_group(conn, base_dn, user.username, everyone_group)
        else:
            print(f"User {user.username} already in everyone group: {everyone_group}", file=sys.stderr)

    if community_group:
        user_groups = [g[1]["cn"][0].decode('utf-8') for g in get_user_groups(conn, base_dn, user.username)]
        if community_group not in user_groups:
            print(f"Adding user {user.username} to community group: {community_group}", file=sys.stderr)
            add_user_to_group(conn, base_dn, user.username, community_group)
        else:
            print(f"User {user.username} already in community group: {community_group}", file=sys.stderr)

    return user.username


def add_user_to_group(conn, base_dn, username, group):
    mod_group = [
        (
            ldap.MOD_ADD,
            "memberUid",
            [username.encode("UTF-8")],
        )
    ]
    return conn.modify_s(
        f"cn={group},ou=Groups,{base_dn}",
        mod_group,
    )


def remove_user_from_group(conn, base_dn, username, group):
    mod_group = [
        (
            ldap.MOD_DELETE,
            "memberUid",
            [username.encode("UTF-8")],
        )
    ]
    return conn.modify_s(
        f"cn={group},ou=Groups,{base_dn}",
        mod_group,
    )


def delete_user(conn, base_dn, username):
    return conn.delete_s(
        f"uid={username},ou=People,{base_dn}",
    )


def change_password(conn, base_dn, username, password):
    return conn.passwd_s(f"uid={username},ou=People,{base_dn}", None, password)


def shadow_last_change(conn, base_dn, days_since_epoch, username):
    # Validate input parameter
    shadow_last_change_value = validate_shadow_last_change(days_since_epoch)

    mod_shadow = [
        (
            ldap.MOD_DELETE,
            "shadowLastChange",
            None,
        ),
        (
            ldap.MOD_ADD,
            "shadowLastChange",
            [str(shadow_last_change_value).encode("UTF-8")],
        ),
    ]
    return conn.modify_s(
        f"uid={username},ou=People,{base_dn}",
        mod_shadow,
    )


def decode_ldap_str_attr(attrs_dict, attr_name: str) -> str | None:
    """Decode LDAP string attribute."""
    attr_value = attrs_dict.get(attr_name)
    if not attr_value:
        return None

    # Get first value if it's a list
    value = attr_value[0] if isinstance(attr_value, list) else attr_value

    if isinstance(value, bytes):
        return value.decode('utf-8')

    return str(value) if value else None


def decode_ldap_int_attr(attrs_dict, attr_name: str) -> int | None:
    """Decode LDAP integer attribute."""
    attr_value = attrs_dict.get(attr_name)
    if not attr_value:
        return None

    # Get first value if it's a list
    value = attr_value[0] if isinstance(attr_value, list) else attr_value

    if isinstance(value, bytes):
        value = value.decode('utf-8')

    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def decode_ldap_list_attr(attrs_dict, attr_name: str) -> list[str] | None:
    """Decode LDAP list attribute."""
    attr_value = attrs_dict.get(attr_name)
    if not attr_value:
        return None

    result = []
    for item in attr_value:
        if isinstance(item, bytes):
            result.append(item.decode('utf-8'))
        else:
            result.append(str(item))

    return result if result else None


def parse_user_attributes(user_result):
    """
    Parse LDAP user search result into a structured dictionary.

    Args:
        user_result: LDAP search result from get_user()

    Returns:
        Dictionary with parsed user attributes or None if user not found
    """
    if not user_result or len(user_result) == 0:
        return None

    # LDAP result format: [(dn, attributes_dict)]
    user_attrs = user_result[0][1]

    return {
        "uid_number": decode_ldap_int_attr(user_attrs, 'uidNumber'),
        "gid_number": decode_ldap_int_attr(user_attrs, 'gidNumber'),
        "given_name": decode_ldap_str_attr(user_attrs, 'givenName'),
        "surname": decode_ldap_str_attr(user_attrs, 'sn'),
        "common_name": decode_ldap_str_attr(user_attrs, 'cn'),
        "email": decode_ldap_str_attr(user_attrs, 'mail'),
        "department": decode_ldap_str_attr(user_attrs, 'departmentNumber'),
        "organization": decode_ldap_str_attr(user_attrs, 'o'),
        "title": decode_ldap_str_attr(user_attrs, 'title'),
        "home_directory": decode_ldap_str_attr(user_attrs, 'homeDirectory'),
        "login_shell": decode_ldap_str_attr(user_attrs, 'loginShell'),
        "shadow_last_change": decode_ldap_int_attr(user_attrs, 'shadowLastChange'),
        "shadow_min": decode_ldap_int_attr(user_attrs, 'shadowMin'),
        "shadow_max": decode_ldap_int_attr(user_attrs, 'shadowMax'),
        "shadow_warning": decode_ldap_int_attr(user_attrs, 'shadowWarning'),
        "shadow_inactive": decode_ldap_int_attr(user_attrs, 'shadowInactive'),
        "object_classes": decode_ldap_list_attr(user_attrs, 'objectClass')
    }


def parse_group_attributes(group_result):
    """
    Parse LDAP group search result into a structured dictionary.

    Args:
        group_result: LDAP search result tuple from get_groups() - (dn, attributes_dict)

    Returns:
        Dictionary with parsed group attributes
    """
    # LDAP result format: (dn, attributes_dict)
    group_attrs = group_result[1]

    return {
        "name": decode_ldap_str_attr(group_attrs, 'cn'),
        "gid_number": decode_ldap_int_attr(group_attrs, 'gidNumber'),
        "display_name": decode_ldap_str_attr(group_attrs, 'displayName'),
        "description": decode_ldap_str_attr(group_attrs, 'description'),
        "samba_group_type": decode_ldap_int_attr(group_attrs, 'sambaGroupType'),
        "samba_sid": decode_ldap_str_attr(group_attrs, 'sambaSID'),
        "object_classes": decode_ldap_list_attr(group_attrs, 'objectClass')
    }


def modify_user_attribute(conn, base_dn, username, attribute, value):
    """
    Modify a single attribute for a user in LDAP.

    This function updates a user's LDAP attribute with a new value using
    the MOD_REPLACE operation, which replaces the existing value(s) with
    the new value.

    Args:
        conn: LDAP connection object
        base_dn: LDAP base distinguished name
        username: Username to modify
        attribute: LDAP attribute name to modify (e.g., 'mail', 'givenName', 'sn', 'cn')
        value: New value for the attribute

    Returns:
        LDAP modify result

    Raises:
        ldap.LDAPError: If the LDAP modification fails
        ValueError: If value is empty
    """
    if not value:
        raise ValueError(f"Value cannot be empty for attribute '{attribute}'")

    # Encode value to bytes for LDAP
    encoded_value = value.encode("UTF-8") if isinstance(value, str) else value

    mod_attrs = [
        (
            ldap.MOD_REPLACE,
            attribute,
            [encoded_value],
        ),
    ]

    return conn.modify_s(
        f"uid={username},ou=People,{base_dn}",
        mod_attrs,
    )