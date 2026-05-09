from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.models.customer import CustomerContacts
from app.services.access_service import AccessContext, get_access_context
from app.services.email_service import email_service
from app.api.v1.quotations import _get_quot_or_403

router = APIRouter()


class SendQuotationEmailRequest(BaseModel):
    quotId: int
    contactId: int
    subject: Optional[str] = None
    htmlBody: Optional[str] = None


class SmtpTestRequest(BaseModel):
    companyId: int


@router.post("/send-quotation")
def send_quotation_email(
    data: SendQuotationEmailRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    ctx: AccessContext = Depends(get_access_context),
):
    smtp_config = email_service.get_smtp_config(db, current_user.company_id)
    if not smtp_config:
        raise HTTPException(
            status_code=400,
            detail="SMTP is not configured for this company",
        )

    # Route the quotation through the full F2/F5/F6 pipeline used elsewhere in
    # the quotation API. Was: bare `quotId == data.quotId, isActive == True`,
    # which let any authenticated user blast another tenant's quotation
    # through this company's SMTP server to an arbitrary contact — both an
    # IDOR and a phishing primitive.
    quotation = _get_quot_or_403(db, data.quotId, ctx)

    contact = db.query(CustomerContacts).filter(
        CustomerContacts.customerContactId == data.contactId,
        CustomerContacts.companyId == current_user.company_id,
        CustomerContacts.isActive == True,
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    to_email = contact.personalEmail or contact.officeEmail
    if not to_email:
        raise HTTPException(status_code=400, detail="Contact has no email address")

    # Strip CR/LF before the subject lands in a MIME header. Without this, a
    # subject like "x\r\nBcc: attacker@evil.com" lets a caller append headers
    # and silently fan the email out to attacker-chosen addresses.
    raw_subject = data.subject or f"Quotation {quotation.quotNo}"
    subject = raw_subject.replace("\r", "").replace("\n", "")
    body = data.htmlBody or f"""
    <h2>Quotation: {quotation.quotNo}</h2>
    <p>Dear {contact.contactPersonName or 'Customer'},</p>
    <p>Please find the quotation details below.</p>
    <p>Quotation No: {quotation.quotNo}</p>
    <p>Date: {quotation.quotDate}</p>
    <p>Subject: {quotation.subject or ''}</p>
    <br/>
    <p>Best Regards</p>
    """

    try:
        email_service.send_email(
            smtp_config=smtp_config,
            to_email=to_email,
            subject=subject,
            html_body=body,
        )
        return {"message": f"Email sent to {to_email}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


@router.post("/test-smtp")
def test_smtp_connection(
    data: SmtpTestRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    smtp_config = email_service.get_smtp_config(db, data.companyId)
    if not smtp_config:
        raise HTTPException(status_code=400, detail="SMTP not configured")

    try:
        import smtplib
        with smtplib.SMTP(smtp_config["smtp_host"], smtp_config["smtp_port"]) as server:
            server.starttls()
            if smtp_config.get("mail_password"):
                server.login(smtp_config["mail_from"], smtp_config["mail_password"])
        return {"message": "SMTP connection successful"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SMTP test failed: {str(e)}")
