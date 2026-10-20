import hashlib

from sqlalchemy.orm import Session

from app.core.security import get_bearer_token
from app.models.endpoint import Endpoint
from app.models.mapping import Mapping
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant


class EndpointTenantAssignmentError(Exception):
    pass


def authenticate_installed_endpoint(
    authorization: str | None,
    db: Session,
) -> Endpoint | None:
    token = get_bearer_token(authorization)
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return db.query(Endpoint).filter(Endpoint.token_hash == token_hash).first()


def assign_unassigned_endpoint(db: Session, endpoint: Endpoint, tenant: Tenant) -> bool:
    if endpoint.tenant_id == tenant.id:
        return False
    if endpoint.tenant_id is not None:
        raise EndpointTenantAssignmentError("The endpoint already belongs to another tenant.")
    if db.query(Mapping.id).filter(Mapping.endpoint_id == endpoint.id).first() is not None:
        raise EndpointTenantAssignmentError("Remove existing mappings before assigning this endpoint to a tenant.")
    endpoint.tenant_id = tenant.id
    return True


def authenticate_endpoint_token(authorization: str | None, db: Session) -> tuple[bool, Tenant | None]:
    token = get_bearer_token(authorization)
    if not token:
        return False, None
    token = token.strip()
    if not token:
        return False, None

    global_token = (
        db.query(SystemSetting.value)
        .filter(SystemSetting.key == "global_agent_token")
        .scalar()
    )
    if global_token and token == global_token:
        return True, None

    tenant = db.query(Tenant).filter(Tenant.agent_token == token).first()
    return tenant is not None, tenant


def validate_endpoint_auth(authorization: str | None, db: Session) -> bool:
    is_valid, _ = authenticate_endpoint_token(authorization, db)
    return is_valid
