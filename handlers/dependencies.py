"""
Shared dependencies for Portal Conductor API handlers.

This module provides access to shared resources like configuration values
and service connections without creating circular imports.
"""

from typing import Any

# Global variables that will be set by main.py
_config: dict[str, Any] | None = None
_ldap_conn: Any = None
_ds_api: Any = None
_terrain_api: Any = None
_email_api: Any = None
_smtp_service: Any = None
_formation_api: Any = None

# Configuration values
_ldap_community_group = None
_ldap_everyone_group = None
_ipcservices_user = None
_ds_admin_user = None
_terrain_url = None
_terrain_user = None
_terrain_password = None
_mailman_enabled = None
_mailman_url = None
_mailman_password = None
_ldap_url = None
_ldap_user = None
_ldap_password = None
_ldap_base_dn = None
_irods_host = None
_irods_port = None
_irods_user = None
_irods_password = None
_irods_zone = None
_formation_app_id = None
_formation_app_name = None
_formation_system_id = None


def init_dependencies(
    config,
    ldap_conn,
    ds_api,
    terrain_api,
    email_api,
    smtp_service,
    ldap_community_group,
    ldap_everyone_group,
    ipcservices_user,
    ds_admin_user,
    terrain_url,
    terrain_user,
    terrain_password,
    mailman_enabled,
    mailman_url,
    mailman_password,
    ldap_url,
    ldap_user,
    ldap_password,
    ldap_base_dn,
    irods_host,
    irods_port,
    irods_user,
    irods_password,
    irods_zone,
    formation_api,
    formation_app_id,
    formation_app_name,
    formation_system_id,
):
    """Initialize all dependencies. Called by main.py after setup."""
    global _config, _ldap_conn, _ds_api, _terrain_api, _email_api, _smtp_service, _formation_api
    global _ldap_community_group, _ldap_everyone_group, _ipcservices_user, _ds_admin_user
    global _terrain_url, _terrain_user, _terrain_password, _mailman_enabled, _mailman_url, _mailman_password
    global _ldap_url, _ldap_user, _ldap_password, _ldap_base_dn
    global _irods_host, _irods_port, _irods_user, _irods_password, _irods_zone
    global _formation_app_id, _formation_app_name, _formation_system_id

    _config = config
    _ldap_conn = ldap_conn
    _ds_api = ds_api
    _terrain_api = terrain_api
    _email_api = email_api
    _smtp_service = smtp_service
    _ldap_community_group = ldap_community_group
    _ldap_everyone_group = ldap_everyone_group
    _ipcservices_user = ipcservices_user
    _ds_admin_user = ds_admin_user
    _terrain_url = terrain_url
    _terrain_user = terrain_user
    _terrain_password = terrain_password
    _mailman_enabled = mailman_enabled
    _mailman_url = mailman_url
    _mailman_password = mailman_password
    _ldap_url = ldap_url
    _ldap_user = ldap_user
    _ldap_password = ldap_password
    _ldap_base_dn = ldap_base_dn
    _irods_host = irods_host
    _irods_port = irods_port
    _irods_user = irods_user
    _irods_password = irods_password
    _irods_zone = irods_zone
    _formation_api = formation_api
    _formation_app_id = formation_app_id
    _formation_app_name = formation_app_name
    _formation_system_id = formation_system_id


# Getter functions for accessing dependencies
def get_config():
    return _config


def get_ldap_conn():
    return _ldap_conn


def get_ds_api():
    return _ds_api


def get_terrain_api():
    return _terrain_api


def get_email_api():
    return _email_api


def get_smtp_service():
    return _smtp_service


def get_ldap_community_group():
    return _ldap_community_group


def get_ldap_everyone_group():
    return _ldap_everyone_group


def get_ipcservices_user():
    return _ipcservices_user


def get_ds_admin_user():
    return _ds_admin_user


def get_terrain_url():
    return _terrain_url


def get_terrain_user():
    return _terrain_user


def get_terrain_password():
    return _terrain_password


def get_mailman_enabled():
    return _mailman_enabled


def get_mailman_url():
    return _mailman_url


def get_mailman_password():
    return _mailman_password


def get_ldap_url():
    return _ldap_url


def get_ldap_user():
    return _ldap_user


def get_ldap_password():
    return _ldap_password


def get_ldap_base_dn():
    return _ldap_base_dn


def get_irods_host():
    return _irods_host


def get_irods_port():
    return _irods_port


def get_irods_user():
    return _irods_user


def get_irods_password():
    return _irods_password


def get_irods_zone():
    return _irods_zone


def get_formation_api():
    return _formation_api


def get_formation_app_id():
    return _formation_app_id


def set_formation_app_id(app_id: str) -> None:
    """Update the cached Formation app ID (e.g. after a lazy lookup)."""
    global _formation_app_id
    _formation_app_id = app_id


def get_formation_app_name():
    return _formation_app_name


def get_formation_system_id():
    return _formation_system_id