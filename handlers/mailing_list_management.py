"""
Mailing List Management API handlers.

This module contains all endpoints related to mailing list operations
for managing mailing list memberships via Mailman.
"""

from fastapi import APIRouter, HTTPException

import kinds
from handlers import dependencies

router = APIRouter(prefix="/mailinglists", tags=["Mailing List Management"])


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