from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.authorization import get_authenticated_user, is_super_admin_user, tenant_scoped_query
from app.core.database import get_db
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["administration"])


@router.get("/users")
async def list_users(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not (is_super_admin_user(user) or (user.is_admin and user.tenant_id is not None)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User administration permission required.",
        )
    users = tenant_scoped_query(db.query(User), User, user).order_by(User.created_at.desc()).all()
    tenants = {tenant.id: tenant.name for tenant in db.query(Tenant).all()} if is_super_admin_user(user) else {}
    return [
        {
            "id": account.id,
            "username": account.username,
            "role": account.role,
            "tenant_id": account.tenant_id,
            "tenant_name": tenants.get(account.tenant_id),
            "created_at": account.created_at,
        }
        for account in users
    ]


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
