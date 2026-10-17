import hashlib
import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.authorization import get_authenticated_user, is_super_admin_user, tenant_scoped_query
from app.core.database import get_db
from app.core.security import hash_password
from app.models.connector import DeviceCommand, SiteConnector
from app.models.device import Device, DeviceChannel
from app.models.endpoint import Endpoint
from app.models.event import AutomationEvent
from app.models.mapping import Mapping
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.tenant_invite import TenantInvite
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["administration"])

class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=72)
    role: Literal["tenant_admin", "manager", "standard_user", "viewer"] = "standard_user"
    tenant_id: str | None = None

    @field_validator("username")
    @classmethod
    def trim_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Username is required.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 UTF-8 bytes or fewer.")
        return value


class UserUpdateRequest(BaseModel):
    role: Literal["tenant_admin", "manager", "standard_user", "viewer"]
    tenant_id: str | None = None


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tenant name is required.")
        return value


class InviteCreateRequest(BaseModel):
    tenant_id: str | None = None


class GlobalAgentTokenRequest(BaseModel):
    action: Literal["save", "regenerate"]
    token: str = Field(default="", max_length=512)


def _require_user_admin(user: User) -> None:
    if not (
        is_super_admin_user(user)
        or (user.is_admin and user.tenant_id is not None)
        or (user.role == "manager" and user.tenant_id is not None)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User administration permission required.",
        )


def _make_agent_token(db: Session) -> str:
    while True:
        token = "".join(secrets.choice(string.ascii_letters) for _ in range(32))
        if db.query(Tenant).filter(Tenant.agent_token == token).first() is None:
            return token


def _user_admin_payload(account: User, tenant_names: dict[str, str]) -> dict[str, object]:
    return {
        "id": account.id,
        "username": account.username,
        "role": account.role,
        "tenant_id": account.tenant_id,
        "tenant_name": tenant_names.get(account.tenant_id),
        "created_at": account.created_at,
    }


@router.get("/users")
async def list_users(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    _require_user_admin(user)
    users = tenant_scoped_query(db.query(User), User, user).order_by(User.created_at.desc()).all()
    tenants = {tenant.id: tenant.name for tenant in db.query(Tenant).all()} if is_super_admin_user(user) else {}
    return [
        _user_admin_payload(account, tenants)
        for account in users
    ]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    _require_user_admin(user)
    if db.query(User.id).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is already in use.")
    if is_super_admin_user(user):
        tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first() if payload.tenant_id else None
    else:
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select a valid tenant.")
    account = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_admin=payload.role == "tenant_admin",
        tenant_id=tenant.id,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _user_admin_payload(account, {tenant.id: tenant.name})


@router.patch("/users/{user_id}")
async def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    _require_user_admin(user)
    target = db.query(User).filter(User.id == str(user_id)).first()
    if target is None or is_super_admin_user(target):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if not is_super_admin_user(user) and target.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if target.id == user.id and payload.role != "tenant_admin":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot remove your own admin role.")
    new_tenant_id = target.tenant_id
    if is_super_admin_user(user):
        tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first() if payload.tenant_id else None
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select a valid tenant.")
        new_tenant_id = tenant.id
    if target.is_admin and target.tenant_id and (
        target.tenant_id != new_tenant_id or payload.role != "tenant_admin"
    ):
        remaining_admins = db.query(User.id).filter(
            User.tenant_id == target.tenant_id,
            User.is_admin.is_(True),
            User.id != target.id,
        ).count()
        if remaining_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one tenant admin must remain for this tenant.",
            )
    target.role = payload.role
    target.is_admin = payload.role == "tenant_admin"
    target.tenant_id = new_tenant_id
    db.commit()
    db.refresh(target)
    tenant_names = {
        tenant.id: tenant.name
        for tenant in db.query(Tenant).filter(Tenant.id == target.tenant_id).all()
    } if target.tenant_id else {}
    return _user_admin_payload(target, tenant_names)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    _require_user_admin(user)
    target = db.query(User).filter(User.id == str(user_id)).first()
    if target is None or is_super_admin_user(target):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if not is_super_admin_user(user) and target.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if target.id == user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot delete your own account.")
    if target.is_admin and target.tenant_id:
        remaining_admins = db.query(User.id).filter(
            User.tenant_id == target.tenant_id,
            User.is_admin.is_(True),
            User.id != target.id,
        ).count()
        if remaining_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one tenant admin must remain for this tenant.",
            )
    db.delete(target)
    db.commit()


@router.get("/tenants")
async def list_tenants(
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not is_super_admin_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Super Admin can manage tenants.",
        )
    response.headers["Cache-Control"] = "private, no-store"
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return [
        {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "agent_token": tenant.agent_token,
            "created_at": tenant.created_at,
        }
        for tenant in tenants
    ]


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreateRequest,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not is_super_admin_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the Super Admin can manage tenants.")
    tenant = Tenant(
        name=payload.name,
        slug=f"tenant-{secrets.token_hex(8)}",
        agent_token=_make_agent_token(db),
        created_by_user_id=user.id,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "agent_token": tenant.agent_token,
        "created_at": tenant.created_at,
    }


@router.post("/tenants/{tenant_id}/rotate-agent-token")
async def rotate_tenant_agent_token(
    tenant_id: UUID,
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not is_super_admin_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the Super Admin can manage tenants.")
    tenant = db.query(Tenant).filter(Tenant.id == str(tenant_id)).first()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    tenant.agent_token = _make_agent_token(db)
    tenant.updated_at = datetime.now(UTC)
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return {"message": "Tenant agent token rotated.", "agent_token": tenant.agent_token}


@router.delete("/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not is_super_admin_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the Super Admin can manage tenants.")
    tenant = db.query(Tenant).filter(Tenant.id == str(tenant_id)).first()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    db.query(TenantInvite).filter(TenantInvite.tenant_id == tenant.id).delete(synchronize_session=False)
    connectors = db.query(SiteConnector).filter(SiteConnector.tenant_id == tenant.id).all()
    for connector in connectors:
        db.query(DeviceCommand).filter(DeviceCommand.connector_id == connector.id).delete(synchronize_session=False)
        db.delete(connector)
    for endpoint in db.query(Endpoint).filter(Endpoint.tenant_id == tenant.id).all():
        db.delete(endpoint)
    for device in db.query(Device).filter(Device.tenant_id == tenant.id).all():
        db.query(Mapping).filter(Mapping.device_id == device.id).delete(synchronize_session=False)
        db.query(DeviceChannel).filter(DeviceChannel.device_id == device.id).delete(synchronize_session=False)
        db.delete(device)
    db.query(Mapping).filter(Mapping.tenant_id == tenant.id).delete(synchronize_session=False)
    db.query(AutomationEvent).filter(AutomationEvent.tenant_id == tenant.id).delete(synchronize_session=False)
    db.query(User).filter(User.tenant_id == tenant.id).delete(synchronize_session=False)
    db.delete(tenant)
    db.commit()


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_tenant_invite(
    payload: InviteCreateRequest,
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not (
        is_super_admin_user(user)
        or (user.role in {"tenant_admin", "manager"} and user.tenant_id is not None)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant invite administration required.")
    tenant_id = payload.tenant_id if is_super_admin_user(user) else user.tenant_id
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first() if tenant_id else None
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select a valid tenant.")

    code = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=7)
    invite = TenantInvite(
        tenant_id=tenant.id,
        code_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(),
        created_by_user_id=user.id,
        created_at=datetime.now(UTC),
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return {"id": invite.id, "code": code, "expires_at": expires_at, "tenant_id": tenant.id}


@router.get("/invites")
async def list_tenant_invites(
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not (
        is_super_admin_user(user)
        or (user.role in {"tenant_admin", "manager"} and user.tenant_id is not None)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant invite administration required.")
    invites = db.query(TenantInvite)
    tenant_names: dict[str, str] = {}
    if not is_super_admin_user(user):
        invites = invites.filter(TenantInvite.tenant_id == user.tenant_id)
    else:
        tenant_names = {tenant.id: tenant.name for tenant in db.query(Tenant).all()}
    response.headers["Cache-Control"] = "private, no-store"
    return [
        {
            "id": invite.id,
            "tenant_id": invite.tenant_id,
            "tenant_name": tenant_names.get(invite.tenant_id),
            "created_at": invite.created_at,
            "expires_at": invite.expires_at,
            "used_at": invite.used_at,
            "is_active": invite.used_at is None and _is_invite_unexpired(invite.expires_at),
        }
        for invite in invites.order_by(TenantInvite.created_at.desc()).all()
    ]


def _is_invite_unexpired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > datetime.now(UTC)


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_tenant_invite(
    invite_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not (
        is_super_admin_user(user)
        or (user.role in {"tenant_admin", "manager"} and user.tenant_id is not None)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant invite administration required.")
    invite = db.query(TenantInvite).filter(TenantInvite.id == str(invite_id)).first()
    if invite is None or (not is_super_admin_user(user) and invite.tenant_id != user.tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")
    db.delete(invite)
    db.commit()


@router.put("/tenant-agent-token")
async def rotate_own_tenant_agent_token(
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if user.role not in {"tenant_admin", "manager"} or not user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant administrator access required.")
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    tenant.agent_token = _make_agent_token(db)
    tenant.updated_at = datetime.now(UTC)
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return {"message": "Tenant agent token rotated.", "agent_token": tenant.agent_token}


@router.put("/global-agent-token")
async def update_global_agent_token(
    payload: GlobalAgentTokenRequest,
    response: Response,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not is_super_admin_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the Super Admin can change this token.")
    setting = db.query(SystemSetting).filter(SystemSetting.key == "global_agent_token").first()
    if setting is None:
        setting = SystemSetting(key="global_agent_token", value=secrets.token_urlsafe(32))
        db.add(setting)
        db.flush()
    if payload.action == "regenerate":
        setting.value = secrets.token_urlsafe(32)
    else:
        token = payload.token.strip()
        if len(token) < 16:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Agent tokens must be between 16 and 512 characters.",
            )
        if db.query(Tenant.id).filter(Tenant.agent_token == token).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That token is already assigned to a tenant.",
            )
        setting.value = token
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return {"message": "System-wide agent token updated.", "global_token": setting.value}
