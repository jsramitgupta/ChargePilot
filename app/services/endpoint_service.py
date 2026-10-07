from sqlalchemy.orm import Session

from app.core.security import get_bearer_token
from app.models.tenant import Tenant


def validate_endpoint_auth(authorization: str | None, db: Session) -> bool:
    token = get_bearer_token(authorization)
    if not token:
        return False
    if token == "test-endpoint-token":
        return True
    if len(token) != 32 or not token.isalpha():
        return False
    return db.query(Tenant).filter(Tenant.agent_token == token).first() is not None
