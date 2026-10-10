from sqlalchemy.orm import Session

from app.core.security import get_bearer_token
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant


def authenticate_endpoint_token(authorization: str | None, db: Session) -> tuple[bool, Tenant | None]:
    token = get_bearer_token(authorization)
    if not token:
        return False, None
    global_token = (
        db.query(SystemSetting.value)
        .filter(SystemSetting.key == "global_agent_token")
        .scalar()
    )
    if global_token and token == global_token:
        return True, None
    if len(token) != 32 or not token.isalpha():
        return False, None
    tenant = db.query(Tenant).filter(Tenant.agent_token == token).first()
    return tenant is not None, tenant


def validate_endpoint_auth(authorization: str | None, db: Session) -> bool:
    is_valid, _ = authenticate_endpoint_token(authorization, db)
    return is_valid
