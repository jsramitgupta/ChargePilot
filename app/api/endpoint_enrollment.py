import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authorization import get_authenticated_user, is_super_admin_user, tenant_scoped_query
from app.core.config import settings
from app.core.database import get_db
from app.models.endpoint import Endpoint
from app.models.endpoint_enrollment import EndpointEnrollment
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.endpoint_enrollment import (
    EndpointEnrollmentCreate,
    EndpointEnrollmentCreated,
    EndpointEnrollmentCredentials,
    EndpointEnrollmentExchange,
    EndpointEnrollmentInfo,
    EndpointEnrollmentToken,
)
from app.services.endpoint_service import authenticate_installed_endpoint
from app.services.local_key_service import decrypt_endpoint_enrollment_code, encrypt_endpoint_enrollment_code

router = APIRouter(tags=["endpoint enrollment"])
ENROLLMENT_TTL = timedelta(hours=24)
MAX_ACTIVE_ENROLLMENTS_PER_ADMIN = 5


@router.post("/endpoint-enrollment/deregister", status_code=status.HTTP_204_NO_CONTENT)
async def deregister_installed_endpoint(
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    endpoint = authenticate_installed_endpoint(authorization, db)
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid per-install endpoint credential is required.",
        )
    endpoint.token_hash = None
    endpoint.automation_enabled = False
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def _require_admin(user: User) -> None:
    if not (
        is_super_admin_user(user)
        or (user.is_admin and user.tenant_id is not None)
        or (user.role == "manager" and user.tenant_id is not None)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Endpoint enrollment permission required.",
        )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@router.post(
    "/admin/endpoint-enrollments",
    response_model=EndpointEnrollmentCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint_enrollment(
    payload: EndpointEnrollmentCreate,
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)

    if is_super_admin_user(user):
        tenant_id = str(payload.tenant_id) if payload.tenant_id else None
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first() if tenant_id else None
    else:
        if payload.tenant_id is not None and str(payload.tenant_id) != user.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied.")
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        tenant_id = tenant.id if tenant else None

    if tenant is None or tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Select a valid tenant for this endpoint enrollment.",
        )

    locked_user = db.query(User).filter(User.id == user.id).with_for_update().first()
    if locked_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    now = datetime.now(UTC)
    active_count = (
        db.query(EndpointEnrollment)
        .filter(
            EndpointEnrollment.created_by_user_id == user.id,
            EndpointEnrollment.revoked_at.is_(None),
            EndpointEnrollment.expires_at > now,
        )
        .count()
    )
    if active_count >= MAX_ACTIVE_ENROLLMENTS_PER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have 5 active enrollment tokens. Revoke one or wait for a token to expire before creating another.",
        )

    raw_code = secrets.token_urlsafe(32)
    expires_at = now + ENROLLMENT_TTL
    enrollment = EndpointEnrollment(
        tenant_id=tenant_id,
        created_by_user_id=user.id,
        platform=None,
        code_hash=hashlib.sha256(raw_code.encode("utf-8")).hexdigest(),
        encrypted_code=encrypt_endpoint_enrollment_code(raw_code),
        expires_at=expires_at,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    response.headers["Cache-Control"] = "private, no-store"
    return EndpointEnrollmentCreated(
        id=enrollment.id,
        enrollment_code=raw_code,
        expires_at=expires_at,
    )


@router.get("/admin/endpoint-enrollments", response_model=list[EndpointEnrollmentInfo])
async def list_endpoint_enrollments(
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    now = datetime.now(UTC)
    enrollments = (
        tenant_scoped_query(
            db.query(EndpointEnrollment, Tenant.name),
            EndpointEnrollment,
            user,
        )
        .join(Tenant, Tenant.id == EndpointEnrollment.tenant_id)
        .filter(
            EndpointEnrollment.created_by_user_id == user.id,
            EndpointEnrollment.revoked_at.is_(None),
            EndpointEnrollment.expires_at > now,
        )
        .order_by(EndpointEnrollment.created_at.desc())
        .limit(MAX_ACTIVE_ENROLLMENTS_PER_ADMIN)
        .all()
    )
    response.headers["Cache-Control"] = "private, no-store"
    return [
        EndpointEnrollmentInfo.model_validate(
            {**enrollment.__dict__, "tenant_name": tenant_name},
        )
        for enrollment, tenant_name in enrollments
    ]


@router.get(
    "/admin/endpoint-enrollments/{enrollment_id}/token",
    response_model=EndpointEnrollmentToken,
)
async def reveal_endpoint_enrollment_token(
    enrollment_id: str,
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    enrollment = (
        tenant_scoped_query(db.query(EndpointEnrollment), EndpointEnrollment, user)
        .filter(
            EndpointEnrollment.id == enrollment_id,
            EndpointEnrollment.created_by_user_id == user.id,
            EndpointEnrollment.revoked_at.is_(None),
            EndpointEnrollment.expires_at > datetime.now(UTC),
        )
        .first()
    )
    if enrollment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active enrollment token not found.")
    if enrollment.encrypted_code is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This token predates secure token reveal. Revoke it and create a new token.",
        )
    response.headers["Cache-Control"] = "private, no-store"
    return EndpointEnrollmentToken(
        id=enrollment.id,
        enrollment_code=decrypt_endpoint_enrollment_code(enrollment.encrypted_code),
        expires_at=enrollment.expires_at,
    )


@router.post(
    "/endpoint-enrollment/exchange",
    response_model=EndpointEnrollmentCredentials,
    status_code=status.HTTP_201_CREATED,
)
async def exchange_endpoint_enrollment(
    payload: EndpointEnrollmentExchange,
    response: Response,
    db: Session = Depends(get_db),
):
    if payload.platform not in settings.enabled_telemetry_platforms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Telemetry enrollment for {payload.platform} is disabled.",
        )

    code_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    enrollment = (
        db.query(EndpointEnrollment)
        .filter(EndpointEnrollment.code_hash == code_hash)
        .with_for_update()
        .first()
    )
    now = datetime.now(UTC)
    if (
        enrollment is None
        or enrollment.revoked_at is not None
        or _utc(enrollment.expires_at) <= now
        or (enrollment.platform is not None and enrollment.used_at is not None)
        or (enrollment.platform is not None and enrollment.platform != payload.platform)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Enrollment token is invalid, expired, revoked, or for a different platform.",
        )

    credential = secrets.token_urlsafe(32)
    endpoint = Endpoint(
        id=str(uuid4()),
        tenant_id=enrollment.tenant_id,
        installation_id=str(payload.installation_id),
        platform=payload.platform,
        device_class=payload.device_class,
        name=payload.hostname,
        hostname=payload.hostname,
        battery_percentage=0,
        charging=False,
        ac_connected=None,
        enabled=True,
        automation_enabled=True,
        token_hash=hashlib.sha256(credential.encode("utf-8")).hexdigest(),
    )
    if enrollment.platform is not None:
        enrollment.used_at = now
    enrollment.enrollment_count += 1
    enrollment.last_used_at = now
    db.add(endpoint)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This installation is already enrolled. Revoke or remove the existing endpoint before re-enrolling.",
        ) from exc

    response.headers["Cache-Control"] = "private, no-store"
    return EndpointEnrollmentCredentials(
        endpoint_id=endpoint.id,
        installation_id=payload.installation_id,
        platform=endpoint.platform,
        credential=credential,
    )


@router.delete("/admin/endpoint-enrollments/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_endpoint_enrollment(
    enrollment_id: str,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    enrollment = (
        tenant_scoped_query(db.query(EndpointEnrollment), EndpointEnrollment, user)
        .filter(EndpointEnrollment.id == enrollment_id)
        .first()
    )
    if enrollment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found.")
    if enrollment.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Enrollment token is already revoked.")
    enrollment.revoked_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/endpoints/{endpoint_id}/credential/revoke")
async def revoke_endpoint_credential(
    endpoint_id: str,
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    endpoint = (
        tenant_scoped_query(db.query(Endpoint), Endpoint, user)
        .filter(Endpoint.id == endpoint_id)
        .first()
    )
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found.")
    if endpoint.token_hash is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This endpoint does not use an installation credential.",
        )
    endpoint.token_hash = None
    endpoint.automation_enabled = False
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return {"status": "revoked"}
