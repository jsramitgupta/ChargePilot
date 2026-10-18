import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode

from app.core.config import settings


logger = logging.getLogger("chargepilot.email")


def build_verification_url(frontend_url: str, token: str) -> str:
    return f"{frontend_url.rstrip('/')}/verify-email?{urlencode({'token': token})}"


def build_account_invitation_url(frontend_url: str, token: str) -> str:
    return f"{frontend_url.rstrip('/')}/accept-invitation?{urlencode({'code': token})}"


def send_verification_email(*, recipient: str, username: str, verification_url: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Verify your ChargePilot account"
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = recipient
    message.set_content(
        f"Hello {username},\n\n"
        "Verify your ChargePilot account by opening this link:\n"
        f"{verification_url}\n\n"
        "This link expires in 30 minutes. If you did not request this account, "
        "you can ignore this email."
    )
    _send_message(message)


def send_account_invitation_email(
    *,
    recipient: str,
    username: str,
    role: str,
    tenant_name: str,
    setup_code: str,
    invitation_url: str,
    expires_at: str,
) -> None:
    message = EmailMessage()
    message["Subject"] = "Your ChargePilot account invitation"
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = recipient
    message.set_content(
        f"Hello {username},\n\n"
        f"You have been invited to {tenant_name} as {role.replace('_', ' ')}.\n\n"
        f"Username: {username}\n"
        f"One-time setup code: {setup_code}\n\n"
        "Open this link to set your password and activate your account:\n"
        f"{invitation_url}\n\n"
        f"This invitation expires on {expires_at}. The setup code can only be used once.\n"
        "If you were not expecting this invitation, you can ignore this email."
    )
    _send_message(message)


def send_support_email(
    *,
    recipient: str,
    reply_email: str,
    subject: str,
    body: str,
    username: str,
    tenant_name: str | None,
) -> None:
    message = EmailMessage()
    message["Subject"] = f"[ChargePilot Support] {subject}"
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = recipient
    message["Reply-To"] = reply_email
    message.set_content(
        f"Support request from {username}\n"
        f"Tenant: {tenant_name or 'System'}\n"
        f"Reply to: {reply_email}\n\n"
        f"{body}"
    )
    _send_message(message)


def _send_message(message: EmailMessage) -> None:
    if not settings.smtp_configured:
        raise RuntimeError("SMTP is not configured.")
    try:
        smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_class(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_use_starttls and not settings.smtp_use_ssl:
                client.ehlo()
                client.starttls()
                client.ehlo()
            client.login(
                settings.smtp_username,
                settings.smtp_password.get_secret_value(),
            )
            client.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Could not deliver email through configured SMTP.")
        raise