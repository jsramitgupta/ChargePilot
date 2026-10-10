from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import false
from sqlalchemy.orm import Query, Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User


def is_super_admin_user(user: User | None) -> bool:
    if user is None:
        return False
    return user.username == settings.admin_username or user.role == "super_admin"


def tenant_scoped_query(query: Query, model: type, user: User) -> Query:
    if is_super_admin_user(user):
        return query
    if user.tenant_id is None:
        return query.filter(false())
    return query.filter(model.tenant_id == user.tenant_id)


def get_authenticated_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    user_id = request.session.get("user_id")
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if user is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user
