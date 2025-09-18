"""
Email Management API handlers.

This module contains all endpoints related to email operations including
mailing list management and SMTP email sending.
"""

from fastapi import APIRouter, HTTPException

import kinds
from handlers import dependencies

router = APIRouter(prefix="/emails", tags=["Email Management"])


@router.delete("/lists/{list_name}/addresses/{addr}", status_code=200, response_model=kinds.EmailListResponse)
def remove_addr_from_list(list_name: str, addr: str):
    """
    Remove an email address from a mailing list.

    If Mailman integration is enabled, removes the specified email address
    from the given mailing list.

    Args:
        list_name: The name of the mailing list
        addr: The email address to remove

    Returns:
        EmailListResponse: Confirmation with list name and email address

    Raises:
        HTTPException: If removal fails or list doesn't exist
    """
    mailman_enabled = dependencies.get_mailman_enabled()
    email_api = dependencies.get_email_api()

    if mailman_enabled:
        email_api.remove_member(list_name, addr)
    return {"list": list_name, "email": addr}


@router.post("/lists/{list_name}/addresses/{addr}", status_code=200, response_model=kinds.EmailListResponse)
def add_addr_to_list(list_name: str, addr: str):
    """
    Add an email address to a mailing list.

    If Mailman integration is enabled, adds the specified email address
    to the given mailing list.

    Args:
        list_name: The name of the mailing list
        addr: The email address to add

    Returns:
        EmailListResponse: Confirmation with list name and email address

    Raises:
        HTTPException: If addition fails or list doesn't exist
    """
    mailman_enabled = dependencies.get_mailman_enabled()
    email_api = dependencies.get_email_api()

    if mailman_enabled:
        email_api.add_member(list_name, addr)
    return {"list": list_name, "email": addr}


@router.post("/send", status_code=200, response_model=kinds.EmailResponse)
def send_email(request: kinds.EmailRequest):
    """
    Send an email via SMTP.

    This endpoint provides email sending functionality to replace direct
    sendmail usage in the portal. It supports both text and HTML email
    bodies, BCC recipients, and configurable sender addresses.

    Args:
        request: Email request containing recipient(s), subject, body, and optional fields

    Returns:
        EmailResponse: Success status and message

    Raises:
        HTTPException: If email sending fails or required fields are missing
    """
    smtp_service = dependencies.get_smtp_service()

    if not request.text_body and not request.html_body:
        raise HTTPException(
            status_code=400, detail="Either text_body or html_body must be provided"
        )

    success = smtp_service.send_email(
        to=request.to,
        subject=request.subject,
        text_body=request.text_body,
        html_body=request.html_body,
        from_email=request.from_email,
        bcc=request.bcc,
    )

    if success:
        return {"success": True, "message": "Email sent successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email")