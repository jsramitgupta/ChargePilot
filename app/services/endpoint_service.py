from sqlalchemy.orm import Session

from app.core.security import get_bearer_token
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant


def validate_endpoint_auth(authorization: str | None, db: Session) -> bool:
    token = get_bearer_token(authorization)
    if not token:
        return False
    global_token = (
        db.query(SystemSetting.value)
        .filter(SystemSetting.key == "global_agent_token")
        .scalar()
    )
    if global_token and token == global_token:
        return True
    if len(token) != 32 or not token.isalpha():
        return False
    return db.query(Tenant).filter(Tenant.agent_token == token).first() is not None
