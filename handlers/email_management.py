"""
Email Management API handlers.

This module contains endpoints for SMTP email sending functionality.
For mailing list management operations, see the Mailing List Management module.
"""

from fastapi import APIRouter, HTTPException

import kinds
from handlers import dependencies
from handlers.auth import AuthDep

router = APIRouter(prefix="/emails", tags=["Email Management"])


@router.post("/send", status_code=200, response_model=kinds.EmailResponse)
def send_email(request: kinds.EmailRequest, current_user: AuthDep):
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