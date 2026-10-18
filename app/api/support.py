import logging
import re
import smtplib

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.authorization import get_authenticated_user
from app.core.config import settings
from app.core.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.services.support_email import send_support_email

router = APIRouter(prefix="/support", tags=["support"])
logger = logging.getLogger("chargepilot.support")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SupportEmailRequest(BaseModel):
    reply_email: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=10, max_length=5000)

    @field_validator("reply_email")
    @classmethod
    def validate_reply_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid reply email address.")
        return value

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        value = value.strip()
        if not value or "\r" in value or "\n" in value:
            raise ValueError("Enter a subject on one line.")
        return value

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("Please include at least 10 characters in your message.")
        return value


@router.get("/config")
def get_support_configuration(_: User = Depends(get_authenticated_user)):
    return {
        "configured": settings.smtp_configured,
        "recipient": settings.support_recipient,
    }


@router.post("/email", status_code=status.HTTP_202_ACCEPTED)
async def create_support_email(
    payload: SupportEmailRequest,
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not settings.smtp_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Support email is unavailable because SMTP is not configured.",
        )

    try:
        await run_in_threadpool(
            send_support_email,
            recipient=settings.support_recipient,
            reply_email=payload.reply_email,
            subject=payload.subject,
            body=payload.body,
            username=user.username,
            tenant_name=db.query(Tenant.name).filter(Tenant.id == user.tenant_id).scalar()
            if user.tenant_id
            else None,
        )
    except (OSError, smtplib.SMTPException, RuntimeError):
        logger.exception("Support email delivery failed for user %s.", user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Your message could not be sent. Please try again later.",
        ) from None

    response.headers["Cache-Control"] = "no-store"
    return {"message": "Your message has been sent to ChargePilot support."}