import hashlib
import logging
import secrets
import smtplib
import string
from datetime import UTC, datetime, timedelta
import re
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.authorization import get_authenticated_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models.account_invitation import AccountInvitation
from app.models.email_verification import EmailVerification
from app.models.tenant import Tenant
from app.models.tenant_invite import TenantInvite
from app.models.user import User
from app.services.support_email import build_verification_url, send_verification_email

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("chargepilot.auth")
TURNSTILE_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
EMAIL_VERIFICATION_TTL = timedelta(minutes=30)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _generate_agent_token(db: Session) -> str:
    while True:
        token = "".join(secrets.choice(string.ascii_letters) for _ in range(32))
        if db.query(Tenant).filter(Tenant.agent_token == token).first() is None:
            return token


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=12, max_length=72)

    @field_validator("new_password")
    @classmethod
    def validate_bcrypt_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("New password must be 72 UTF-8 bytes or fewer.")
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 UTF-8 bytes or fewer.")
        return value


class RegistrationRequest(BaseModel):
    account_type: Literal["standard", "tenant"]
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=72)
    email: str = Field(min_length=3, max_length=254)
    turnstile_token: str = Field(min_length=1, max_length=2048)
    invite_code: str | None = Field(default=None, min_length=20, max_length=128)
    tenant_name: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("username", "email", "invite_code", "tenant_name", mode="before")
    @classmethod
    def trim_registration_fields(cls, value: str | None, info) -> str | None:
        if info.field_name == "email" and isinstance(value, str):
            return value.strip().casefold()
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 UTF-8 bytes or fewer.")
        return value

    @model_validator(mode="after")
    def validate_registration_mode(self):
        if self.account_type == "standard" and not self.invite_code:
            raise ValueError("A tenant invite code is required for standard user registration.")
        if self.account_type == "tenant" and not self.tenant_name:
            raise ValueError("A tenant name is required to create a tenant.")
        return self


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class InvitationCodeRequest(BaseModel):
    code: str = Field(min_length=32, max_length=128)


class AcceptInvitationRequest(InvitationCodeRequest):
    password: str = Field(min_length=12, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 UTF-8 bytes or fewer.")
        return value


class ResendVerificationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    turnstile_token: str = Field(min_length=1, max_length=2048)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid email address.")
        return value


class ProfileUpdateRequest(BaseModel):
    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        value = value.strip()
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Enter a valid IANA time zone.") from exc
        return value


async def verify_registration_challenge(token: str) -> None:
    secret = settings.turnstile_secret_key.get_secret_value()
    expected_hostname = urlsplit(settings.frontend_url).hostname
    if not settings.turnstile_site_key or not secret or not expected_hostname:
        logger.error("Account registration is disabled because Turnstile is not fully configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account registration is temporarily unavailable.",
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                TURNSTILE_SITEVERIFY_URL,
                data={"secret": secret, "response": token},
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Turnstile verification could not be completed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Human verification is temporarily unavailable. Please try again.",
        ) from None

    if (
        not isinstance(result, dict)
        or result.get("success") is not True
        or result.get("hostname") != expected_hostname
        or result.get("action") != "registration"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Human verification failed. Please complete the challenge again.",
        )


def _user_payload(user: User, tenant: Tenant | None) -> dict[str, object]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "is_admin": bool(user.is_admin),
        "smartlife_user_code": user.smartlife_user_code,
        "timezone": user.timezone,
        "tenant_name": tenant.name if tenant else None,
    }


def _create_email_verification(db: Session, user: User, now: datetime) -> str:
    db.query(EmailVerification).filter(
        EmailVerification.user_id == user.id,
        EmailVerification.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)
    token = secrets.token_urlsafe(32)
    db.add(
        EmailVerification(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            created_at=now,
            expires_at=now + EMAIL_VERIFICATION_TTL,
        )
    )
    return token


async def _send_verification(user: User, token: str) -> None:
    if not settings.smtp_configured or not settings.frontend_url:
        logger.error("Account verification email is unavailable because SMTP is not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account registration is temporarily unavailable because email delivery is not configured.",
        )
    try:
        await run_in_threadpool(
            send_verification_email,
            recipient=user.email or "",
            username=user.username,
            verification_url=build_verification_url(settings.frontend_url, token),
        )
    except (OSError, smtplib.SMTPException, RuntimeError):
        logger.exception("Account verification email delivery failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The verification email could not be sent. Request a new link and try again.",
        ) from None


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username or password is incorrect.",
        )
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email address before signing in.",
        )
    request.session.clear()
    request.session["user_id"] = user.id
    response.headers["Cache-Control"] = "private, no-store"
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first() if user.tenant_id else None
    return {"user": _user_payload(user, tenant)}


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(
    payload: RegistrationRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    if request.session.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sign out before creating another account.",
        )
    await verify_registration_challenge(payload.turnstile_token)
    if not settings.smtp_configured or not settings.frontend_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account registration is temporarily unavailable because email delivery is not fully configured.",
        )
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username is required.")
    if db.query(User.id).filter(User.username == username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is already in use.")
    if db.query(User.id).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email address is already in use.")

    tenant: Tenant
    invite: TenantInvite | None = None
    now = datetime.now(UTC)
    if payload.account_type == "standard":
        code_digest = hashlib.sha256((payload.invite_code or "").encode("utf-8")).hexdigest()
        invite = db.execute(
            select(TenantInvite)
            .where(
                TenantInvite.code_hash == code_digest,
                TenantInvite.used_at.is_(None),
                TenantInvite.expires_at > now,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if invite is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The tenant invite code is invalid, expired, or already used.",
            )
        tenant = db.query(Tenant).filter(Tenant.id == invite.tenant_id).first()
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The invite code is no longer associated with an active tenant.",
            )
        role = "standard_user"
    else:
        tenant_name = (payload.tenant_name or "").strip()
        if not tenant_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tenant name is required.")
        tenant = Tenant(
            name=tenant_name,
            slug=f"tenant-{secrets.token_hex(8)}",
            agent_token=_generate_agent_token(db),
        )
        db.add(tenant)
        db.flush()
        role = "tenant_admin"

    user = User(
        username=username,
        email=payload.email,
        email_verified=False,
        password_hash=hash_password(payload.password),
        tenant_id=tenant.id,
        role=role,
        is_admin=role == "tenant_admin",
        timezone="UTC",
    )
    db.add(user)
    if payload.account_type == "tenant":
        tenant.created_by_user_id = user.id
    if invite is not None:
        invite.used_at = now

    try:
        db.flush()
        verification_token = _create_email_verification(db, user, now)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The username or tenant identifier is already in use.",
        ) from exc

    db.refresh(user)
    db.refresh(tenant)
    response.headers["Cache-Control"] = "no-store"
    await _send_verification(user, verification_token)
    return {"message": "Check your email for a link to verify your account."}


@router.post("/verify-email")
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    now = datetime.now(UTC)
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    verification = db.execute(
        select(EmailVerification)
        .where(
            EmailVerification.token_hash == token_hash,
            EmailVerification.used_at.is_(None),
            EmailVerification.expires_at > now,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if verification is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The verification link is invalid, expired, or already used.",
        )

    user = db.query(User).filter(User.id == verification.user_id).first()
    if user is None or not user.email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The verification link is invalid, expired, or already used.",
        )
    verification.used_at = now
    user.email_verified = True
    db.commit()
    request.session.clear()
    request.session["user_id"] = user.id
    response.headers["Cache-Control"] = "private, no-store"
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first() if user.tenant_id else None
    return {"user": _user_payload(user, tenant)}


@router.post("/invitation-details")
async def get_invitation_details(
    payload: InvitationCodeRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    now = datetime.now(UTC)
    token_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    invitation = db.query(AccountInvitation).filter(
        AccountInvitation.token_hash == token_hash,
        AccountInvitation.used_at.is_(None),
        AccountInvitation.revoked_at.is_(None),
        AccountInvitation.expires_at > now,
    ).first()
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This invitation is invalid, expired, or already used.",
        )
    tenant = db.query(Tenant).filter(Tenant.id == invitation.tenant_id).first()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This invitation is no longer associated with an active tenant.",
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "username": invitation.username,
        "email": invitation.email,
        "role": invitation.role,
        "tenant_name": tenant.name,
        "expires_at": invitation.expires_at,
    }


@router.post("/accept-invitation")
async def accept_account_invitation(
    payload: AcceptInvitationRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    now = datetime.now(UTC)
    token_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    invitation = db.execute(
        select(AccountInvitation)
        .where(
            AccountInvitation.token_hash == token_hash,
            AccountInvitation.used_at.is_(None),
            AccountInvitation.revoked_at.is_(None),
            AccountInvitation.expires_at > now,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This invitation is invalid, expired, or already used.",
        )
    tenant = db.query(Tenant).filter(Tenant.id == invitation.tenant_id).first()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This invitation is no longer associated with an active tenant.",
        )
    if (
        db.query(User.id)
        .filter((User.username == invitation.username) | (func.lower(User.email) == invitation.email))
        .first()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username or email address is already associated with an account.",
        )

    user = User(
        username=invitation.username,
        email=invitation.email,
        email_verified=True,
        password_hash=hash_password(payload.password),
        tenant_id=tenant.id,
        role=invitation.role,
        is_admin=invitation.role == "tenant_admin",
        timezone="UTC",
    )
    invitation.used_at = now
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username or email address is already associated with an account.",
        ) from exc
    request.session.clear()
    request.session["user_id"] = user.id
    response.headers["Cache-Control"] = "private, no-store"
    return {"user": _user_payload(user, tenant)}


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    payload: ResendVerificationRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    await verify_registration_challenge(payload.turnstile_token)
    if not settings.smtp_configured or not settings.frontend_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is temporarily unavailable.",
        )
    response.headers["Cache-Control"] = "no-store"
    user = db.query(User).filter(User.email == payload.email, User.email_verified.is_(False)).first()
    if user is not None:
        now = datetime.now(UTC)
        token = _create_email_verification(db, user, now)
        db.commit()
        await _send_verification(user, token)
    return {"message": "If the account needs verification, a new email has been sent."}


@router.get("/me")
async def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first() if user.tenant_id else None
    return _user_payload(user, tenant)


@router.put("/profile")
async def update_profile(
    payload: ProfileUpdateRequest,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    user.timezone = payload.timezone
    db.commit()
    return {"message": "Time zone saved.", "timezone": user.timezone}


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"status": "logged_out"}


@router.put("/password")
async def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password.",
        )

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password changed."}
