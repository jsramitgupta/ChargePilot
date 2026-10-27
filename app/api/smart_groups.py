import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)
from sqlalchemy.orm import Session

from app.core.authorization import get_authenticated_user, is_super_admin_user
from app.core.database import get_db
from app.models.endpoint import Endpoint
from app.models.smart_group import SensorAssignment, SensorExecution, SmartGroup
from app.models.tenant import Tenant
from app.models.user import User
from app.services.endpoint_service import authenticate_installed_endpoint
from app.services.sensor_service import (
    SENSOR_CATALOG,
    claim_sensor_execution,
    complete_sensor_execution,
    matching_group_endpoint_count,
    matching_group_endpoints,
)

router = APIRouter(tags=["smart groups and sensors"])
MAX_GROUP_RUN_ENDPOINTS = 500
MAX_GROUP_RUN_EXECUTIONS = MAX_GROUP_RUN_ENDPOINTS * len(SENSOR_CATALOG)


class GroupCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platforms: list[Literal["windows", "macos"]] = Field(min_length=1, max_length=2)
    endpoint_ids: list[UUID] | None = Field(default=None, max_length=500)
    name_contains: str | None = Field(default=None, max_length=80)
    battery_min: int | None = Field(default=None, ge=0, le=100)
    battery_max: int | None = Field(default=None, ge=0, le=100)
    charging: bool | None = None

    @field_validator("platforms")
    @classmethod
    def unique_platforms(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Platforms must be unique.")
        return value

    @field_validator("endpoint_ids")
    @classmethod
    def unique_endpoints(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is not None and not value:
            raise ValueError(
                "Select at least one device or leave the target list empty."
            )
        if value is not None and len(set(value)) != len(value):
            raise ValueError("Selected devices must be unique.")
        return value

    @field_validator("name_contains")
    @classmethod
    def clean_name_query(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None

    @model_validator(mode="after")
    def validate_battery_range(self) -> "GroupCriteria":
        if (
            self.battery_min is not None
            and self.battery_max is not None
            and self.battery_min > self.battery_max
        ):
            raise ValueError("Minimum battery level cannot exceed maximum.")
        return self


class SmartGroupWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    criteria: GroupCriteria
    sensor_ids: list[str] = Field(min_length=1, max_length=len(SENSOR_CATALOG))

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Group name cannot be blank.")
        return normalized

    @field_validator("sensor_ids")
    @classmethod
    def validate_sensor_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Sensor selections must be unique.")
        unsupported = set(value) - SENSOR_CATALOG.keys()
        if unsupported:
            raise ValueError(
                "One or more selected sensors are not in the approved catalog."
            )
        return value


class SensorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_token: str = Field(pattern=r"^[A-Za-z0-9_-]{32,128}$")
    value: StrictStr | StrictInt | None = None
    error: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def require_result_or_error(self) -> "SensorReport":
        if (self.error is None) == (self.value is None):
            raise ValueError("Provide either a sensor value or an error.")
        return self


def _require_manager(user: User) -> None:
    if not is_super_admin_user(user) and user.role not in {"tenant_admin", "manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant administrator or manager access is required.",
        )


def _target_tenant_id(user: User, requested_tenant_id: str | None) -> str:
    if is_super_admin_user(user):
        if requested_tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Super Admins must select a tenant.",
            )
        return requested_tenant_id
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not assigned to a tenant.",
        )
    if requested_tenant_id is not None and requested_tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found."
        )
    return user.tenant_id


def _validate_group_targets(
    db: Session,
    *,
    tenant_id: str,
    criteria: GroupCriteria,
) -> None:
    if criteria.endpoint_ids is None:
        return
    endpoint_ids = [str(endpoint_id) for endpoint_id in criteria.endpoint_ids]
    endpoints = (
        db.query(Endpoint)
        .filter(
            Endpoint.id.in_(endpoint_ids),
            Endpoint.tenant_id == tenant_id,
            Endpoint.platform.in_(criteria.platforms),
            Endpoint.installation_id.is_not(None),
            Endpoint.token_hash.is_not(None),
            Endpoint.enabled.is_(True),
        )
        .all()
    )
    if len(endpoints) != len(endpoint_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Selected devices must be enabled, enrolled Windows or macOS endpoints in this workspace.",
        )


def _group_for_user(db: Session, user: User, group_id: str) -> SmartGroup | None:
    query = db.query(SmartGroup).filter(SmartGroup.id == group_id)
    if not is_super_admin_user(user):
        query = query.filter(SmartGroup.tenant_id == user.tenant_id)
    return query.first()


def _serialize_execution(
    execution: SensorExecution, endpoint: Endpoint
) -> dict[str, Any]:
    result = json.loads(execution.result_json) if execution.result_json else None
    return {
        "id": execution.id,
        "sensor_id": execution.sensor_id,
        "sensor_name": SENSOR_CATALOG[execution.sensor_id]["name"],
        "endpoint_id": endpoint.id,
        "endpoint_name": endpoint.name or endpoint.hostname,
        "platform": endpoint.platform,
        "status": execution.status,
        "result": result,
        "error": execution.error,
        "created_at": execution.created_at.isoformat()
        if execution.created_at
        else None,
        "completed_at": execution.completed_at.isoformat()
        if execution.completed_at
        else None,
    }


def _serialize_group(db: Session, group: SmartGroup) -> dict[str, Any]:
    assignments = (
        db.query(SensorAssignment)
        .filter(
            SensorAssignment.group_id == group.id,
            SensorAssignment.tenant_id == group.tenant_id,
            SensorAssignment.enabled.is_(True),
        )
        .order_by(SensorAssignment.sensor_id.asc())
        .all()
    )
    endpoints = matching_group_endpoints(db, group, limit=500)
    endpoint_count = matching_group_endpoint_count(db, group)
    recent = (
        db.query(SensorExecution, Endpoint)
        .join(Endpoint, Endpoint.id == SensorExecution.endpoint_id)
        .filter(
            SensorExecution.group_id == group.id,
            SensorExecution.tenant_id == group.tenant_id,
            Endpoint.tenant_id == group.tenant_id,
        )
        .order_by(SensorExecution.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "id": group.id,
        "tenant_id": group.tenant_id,
        "tenant_name": db.query(Tenant.name)
        .filter(Tenant.id == group.tenant_id)
        .scalar(),
        "name": group.name,
        "criteria": json.loads(group.criteria_json),
        "sensor_ids": [assignment.sensor_id for assignment in assignments],
        "matching_endpoint_count": endpoint_count,
        "matching_endpoints": [
            {
                "id": endpoint.id,
                "name": endpoint.name or endpoint.hostname,
                "platform": endpoint.platform,
                "battery_percentage": endpoint.battery_percentage,
                "last_seen_at": endpoint.last_seen_at.isoformat()
                if endpoint.last_seen_at
                else None,
            }
            for endpoint in endpoints
        ],
        "recent_executions": [
            _serialize_execution(execution, endpoint) for execution, endpoint in recent
        ],
        "created_at": group.created_at.isoformat(),
        "updated_at": group.updated_at.isoformat(),
    }


@router.get("/smart-groups/catalog")
async def get_sensor_catalog(
    _: User = Depends(get_authenticated_user),
) -> list[dict[str, str]]:
    return [
        {"id": sensor_id, **definition}
        for sensor_id, definition in SENSOR_CATALOG.items()
    ]


@router.get("/smart-groups/tenants")
async def list_smart_group_tenants(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> list[dict[str, str]]:
    if is_super_admin_user(user):
        return [
            {"id": tenant.id, "name": tenant.name}
            for tenant in db.query(Tenant).order_by(Tenant.name.asc()).all()
        ]
    if user.tenant_id is None:
        return []
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return [{"id": tenant.id, "name": tenant.name}] if tenant is not None else []


@router.get("/smart-groups")
async def list_smart_groups(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = db.query(SmartGroup)
    if not is_super_admin_user(user):
        if user.tenant_id is None:
            return []
        query = query.filter(SmartGroup.tenant_id == user.tenant_id)
    groups = query.order_by(SmartGroup.updated_at.desc()).limit(100).all()
    return [_serialize_group(db, group) for group in groups]


@router.post("/smart-groups", status_code=status.HTTP_201_CREATED)
async def create_smart_group(
    payload: SmartGroupWrite,
    tenant_id: UUID | None = None,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_manager(user)
    target_tenant_id = _target_tenant_id(user, str(tenant_id) if tenant_id else None)
    if db.query(Tenant.id).filter(Tenant.id == target_tenant_id).first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found."
        )
    _validate_group_targets(db, tenant_id=target_tenant_id, criteria=payload.criteria)
    group = SmartGroup(
        tenant_id=target_tenant_id,
        name=payload.name,
        criteria_json=payload.criteria.model_dump_json(),
        created_by=user.id,
    )
    db.add(group)
    db.flush()
    for sensor_id in payload.sensor_ids:
        db.add(
            SensorAssignment(
                tenant_id=target_tenant_id,
                group_id=group.id,
                sensor_id=sensor_id,
            )
        )
    db.commit()
    db.refresh(group)
    return _serialize_group(db, group)


@router.put("/smart-groups/{group_id}")
async def update_smart_group(
    group_id: UUID,
    payload: SmartGroupWrite,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_manager(user)
    group = _group_for_user(db, user, str(group_id))
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Smart group not found."
        )
    _validate_group_targets(db, tenant_id=group.tenant_id, criteria=payload.criteria)
    group.name = payload.name
    group.criteria_json = payload.criteria.model_dump_json()
    group.updated_at = datetime.now(UTC)
    assignments = {
        assignment.sensor_id: assignment
        for assignment in db.query(SensorAssignment)
        .filter(
            SensorAssignment.group_id == group.id,
            SensorAssignment.tenant_id == group.tenant_id,
        )
        .all()
    }
    for sensor_id, assignment in assignments.items():
        assignment.enabled = sensor_id in payload.sensor_ids
    for sensor_id in payload.sensor_ids:
        if sensor_id not in assignments:
            db.add(
                SensorAssignment(
                    tenant_id=group.tenant_id,
                    group_id=group.id,
                    sensor_id=sensor_id,
                )
            )
    db.commit()
    db.refresh(group)
    return _serialize_group(db, group)


@router.delete("/smart-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_smart_group(
    group_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> Response:
    _require_manager(user)
    group = _group_for_user(db, user, str(group_id))
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Smart group not found."
        )
    db.delete(group)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/smart-groups/{group_id}/run")
async def run_smart_group(
    group_id: UUID,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    _require_manager(user)
    group = _group_for_user(db, user, str(group_id))
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Smart group not found."
        )
    endpoints = matching_group_endpoints(db, group, limit=MAX_GROUP_RUN_ENDPOINTS + 1)
    if len(endpoints) > MAX_GROUP_RUN_ENDPOINTS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This run exceeds the {MAX_GROUP_RUN_ENDPOINTS}-endpoint safety limit. Narrow the group criteria.",
        )
    assignments = (
        db.query(SensorAssignment)
        .filter(
            SensorAssignment.group_id == group.id,
            SensorAssignment.tenant_id == group.tenant_id,
            SensorAssignment.enabled.is_(True),
        )
        .all()
    )
    maximum_execution_count = len(endpoints) * len(assignments)
    if maximum_execution_count > MAX_GROUP_RUN_EXECUTIONS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sensor run exceeds the safety limit.",
        )
    existing_active = {
        (endpoint_id, assignment_id)
        for endpoint_id, assignment_id in (
            db.query(SensorExecution.endpoint_id, SensorExecution.assignment_id)
            .filter(
                SensorExecution.group_id == group.id,
                SensorExecution.tenant_id == group.tenant_id,
                SensorExecution.endpoint_id.in_(
                    [endpoint.id for endpoint in endpoints]
                ),
                SensorExecution.status.in_(("queued", "claimed")),
            )
            .all()
            if endpoints
            else []
        )
    }
    now = datetime.now(UTC)
    queued_endpoint_ids: set[str] = set()
    queued_sensor_count = 0
    for endpoint in endpoints:
        for assignment in assignments:
            if (endpoint.id, assignment.id) in existing_active:
                continue
            db.add(
                SensorExecution(
                    id=str(uuid4()),
                    tenant_id=group.tenant_id,
                    group_id=group.id,
                    assignment_id=assignment.id,
                    endpoint_id=endpoint.id,
                    sensor_id=assignment.sensor_id,
                    status="queued",
                    created_at=now,
                )
            )
            queued_endpoint_ids.add(endpoint.id)
            queued_sensor_count += 1
    db.commit()
    return {
        "queued_endpoints": len(queued_endpoint_ids),
        "queued_sensors": queued_sensor_count,
    }


def _require_installed_endpoint(
    authorization: str | None,
    db: Session,
) -> Endpoint:
    endpoint = authenticate_installed_endpoint(authorization, db)
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid enrolled endpoint credential is required.",
        )
    if (
        endpoint.platform not in {"windows", "macos"}
        or endpoint.installation_id is None
        or endpoint.tenant_id is None
        or not endpoint.enabled
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is not eligible for sensor collection.",
        )
    return endpoint


@router.post("/endpoint-sensors/claim")
async def claim_endpoint_sensor(
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    endpoint = _require_installed_endpoint(authorization, db)
    claimed = claim_sensor_execution(db, endpoint=endpoint)
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    if claimed is None:
        return {"sensor": None}
    execution, claim_token = claimed
    return {
        "sensor": {
            "id": execution.id,
            "sensor_id": execution.sensor_id,
            "claim_token": claim_token,
        }
    }


@router.post("/endpoint-sensors/{execution_id}/report")
async def report_endpoint_sensor(
    execution_id: UUID,
    payload: SensorReport,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    endpoint = _require_installed_endpoint(authorization, db)
    try:
        execution = complete_sensor_execution(
            db,
            endpoint=endpoint,
            execution_id=str(execution_id),
            claim_token=payload.claim_token,
            value=payload.value,
            error=payload.error,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    except PermissionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sensor execution not found."
        )
    if execution.status not in {"completed", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sensor execution is no longer claimable.",
        )
    db.commit()
    return {"status": execution.status}
