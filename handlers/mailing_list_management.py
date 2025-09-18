"""
Mailing List Management API handlers.

This module contains all endpoints related to mailing list operations
for managing mailing list memberships via Mailman.
"""

from fastapi import APIRouter, HTTPException

import kinds
from handlers import dependencies

router = APIRouter(prefix="/mailinglists", tags=["Mailing List Management"])


@router.get("/{listname}/members", status_code=200, response_model=kinds.MailingListMembersResponse)
def list_mailing_list_members(listname: str):
    """
    Retrieve a list of all members in a mailing list.

    This endpoint provides a comprehensive overview of all current members in the specified
    mailing list. It accesses the Mailman 2.1 admin roster interface to retrieve member
    email addresses and returns them in a structured JSON format.

    The endpoint is particularly useful for:
    - Administrative interfaces displaying current mailing list membership
    - Bulk operations requiring knowledge of current subscribers
    - Integration systems that need to verify or audit mailing list membership
    - Reporting and analytics tools for mailing list management
    - User management dashboards showing subscription status across lists
    - Automated systems that need to synchronize mailing list data

    This retrieval operates at the Mailman roster level and extracts member information
    from the admin interface. The returned list includes all active members regardless
    of their subscription preferences or delivery settings.

    Args:
        listname: The name of the mailing list to retrieve members from

    Returns:
        MailingListMembersResponse: Object containing the list name and array of member emails

    Raises:
        HTTPException:
            - 503: If mailing list functionality is not enabled
            - 500: If Mailman query fails due to connection issues, authentication errors,
                   roster privacy restrictions, HTML parsing errors, or other system issues

    Example:
        GET /mailinglists/announcements/members
        Returns: {
            "listname": "announcements",
            "members": [
                "john.doe@example.com",
                "jane.smith@university.edu",
                "admin@organization.org"
            ]
        }

    Note:
        - Accesses the Mailman 2.1 /mailman/admin/{listname}/members interface
        - Requires valid Mailman admin credentials for the service account
        - Parses HTML content to extract member email addresses using regex patterns
        - Filters out common false positives like system and administrative emails
        - Returns emails in sorted order for consistent output
        - May fail if the mailing list roster is configured with strict privacy settings
        - Network failures or Mailman unavailability will result in 500 errors
        - Returns empty member list if no members are found or if parsing fails
        - Admin access is required to view member rosters in most Mailman configurations
    """
    mailman_enabled = dependencies.get_mailman_enabled()
    email_api = dependencies.get_email_api()

    if not mailman_enabled:
        raise HTTPException(
            status_code=503, detail="Mailing list functionality is not enabled"
        )

    try:
        members = email_api.list_members(listname)
        return kinds.MailingListMembersResponse(listname=listname, members=members)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve mailing list members: {str(e)}"
        )


@router.post("/{listname}/members", status_code=200, response_model=kinds.GenericResponse)
def add_to_mailing_list(listname: str, request: kinds.MailingListMemberRequest):
    """
    Add a user to a mailing list.

    Args:
        listname: Mailing list name
        request: Member details

    Returns:
        GenericResponse: Success status and message

    Raises:
        HTTPException: If operation fails or mailman not enabled
    """
    mailman_enabled = dependencies.get_mailman_enabled()
    email_api = dependencies.get_email_api()

    if not mailman_enabled:
        raise HTTPException(
            status_code=503, detail="Mailing list functionality is not enabled"
        )

    try:
        email_api.add_member(listname, request.email)
        return {
            "success": True,
            "message": f"Added {request.email} to mailing list {listname}",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to add user to mailing list: {str(e)}"
        )


@router.delete("/{listname}/members/{email}", status_code=200, response_model=kinds.GenericResponse)
def remove_from_mailing_list(listname: str, email: str):
    """
    Remove a user from a mailing list.

    Args:
        listname: Mailing list name
        email: Email address to remove

    Returns:
        GenericResponse: Success status and message

    Raises:
        HTTPException: If operation fails or mailman not enabled
    """
    mailman_enabled = dependencies.get_mailman_enabled()
    email_api = dependencies.get_email_api()

    if not mailman_enabled:
        raise HTTPException(
            status_code=503, detail="Mailing list functionality is not enabled"
        )

    try:
        email_api.remove_member(listname, email)
        return {
            "success": True,
            "message": f"Removed {email} from mailing list {listname}",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to remove user from mailing list: {str(e)}"
        )


@router.get("/{listname}/members/{email}/exists", status_code=200, response_model=kinds.EmailExistsResponse)
def check_email_exists_in_mailing_list(listname: str, email: str):
    """
    Check if an email address exists in a mailing list.

    This endpoint verifies whether a given email address is a member of the specified
    mailing list in the Mailman system. It provides essential validation for mailing
    list operations and membership management workflows.

    The endpoint is particularly useful for:
    - Pre-validation before attempting mailing list operations
    - Email membership verification for external integrations and services
    - Administrative mailing list management interfaces and dashboards
    - User registration validation to check existing subscriptions
    - Integration systems that need to verify mailing list membership
    - Auditing and reporting tools for mailing list membership tracking

    This check operates at the Mailman roster level and validates whether the email
    address is listed as a member of the mailing list. It accesses the Mailman 2.1
    admin interface to retrieve membership information via the roster page.

    Args:
        listname: The name of the mailing list to check membership in
        email: The email address to check for membership in the mailing list

    Returns:
        EmailExistsResponse: Object containing the email address and existence status

    Raises:
        HTTPException:
            - 503: If mailing list functionality is not enabled
            - 500: If Mailman query fails due to connection, authentication,
                   roster privacy settings, or other Mailman system issues

    Example:
        GET /mailinglists/announcements/members/john.doe@example.com/exists
        Returns: {
            "email": "john.doe@example.com",
            "exists": true
        }

    Note:
        - Requires valid Mailman admin credentials for the service account
        - May fail if the mailing list roster is configured as private
        - Uses case-insensitive email matching for membership checking
        - Network or authentication failures will result in 500 errors, not false
        - List privacy settings may prevent roster access even with admin credentials
    """
    mailman_enabled = dependencies.get_mailman_enabled()
    email_api = dependencies.get_email_api()

    if not mailman_enabled:
        raise HTTPException(
            status_code=503, detail="Mailing list functionality is not enabled"
        )

    try:
        exists = email_api.member_exists(listname, email)
        return kinds.EmailExistsResponse(email=email, exists=exists)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check email existence in mailing list: {str(e)}"
        )
