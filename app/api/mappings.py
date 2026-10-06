from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.mapping import Mapping
from app.schemas.mapping import MappingCreate, MappingRead, MappingUpdate

router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.get("", response_model=list[MappingRead])
async def list_mappings(db: Session = Depends(get_db)):
    return db.query(Mapping).order_by(Mapping.created_at.desc()).all()


def _ensure_unique_mapping(db: Session, endpoint_id: str, device_id: str, mapping_id: str | None = None):
    queryset = db.query(Mapping).filter(Mapping.endpoint_id == endpoint_id, Mapping.device_id == device_id)
    if mapping_id is not None:
        queryset = queryset.filter(Mapping.id != mapping_id)

    existing = queryset.first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A mapping for this endpoint and switch already exists.",
        )


@router.post("", response_model=MappingRead, status_code=status.HTTP_201_CREATED)
async def create_mapping(payload: MappingCreate, db: Session = Depends(get_db)):
    endpoint_id = str(payload.endpoint_id)
    device_id = str(payload.device_id)
    _ensure_unique_mapping(db, endpoint_id, device_id)

    mapping = Mapping(
        endpoint_id=endpoint_id,
        device_id=device_id,
        channel_id=str(payload.channel_id) if payload.channel_id is not None else None,
        enabled=payload.enabled,
        on_threshold=payload.on_threshold,
        off_threshold=payload.off_threshold,
        minimum_state_change_interval=payload.minimum_state_change_interval,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


@router.get("/{mapping_id}", response_model=MappingRead)
async def get_mapping(mapping_id: UUID, db: Session = Depends(get_db)):
    mapping = db.query(Mapping).filter(Mapping.id == str(mapping_id)).first()
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found.")
    return mapping


@router.put("/{mapping_id}", response_model=MappingRead)
async def update_mapping(mapping_id: UUID, payload: MappingUpdate, db: Session = Depends(get_db)):
    mapping = db.query(Mapping).filter(Mapping.id == str(mapping_id)).first()
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found.")

    endpoint_id = mapping.endpoint_id
    device_id = mapping.device_id

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            if field in {"endpoint_id", "device_id", "channel_id"}:
                setattr(mapping, field, str(value))
            else:
                setattr(mapping, field, value)

    if payload.endpoint_id is not None or payload.device_id is not None:
        endpoint_id = str(payload.endpoint_id) if payload.endpoint_id is not None else mapping.endpoint_id
        device_id = str(payload.device_id) if payload.device_id is not None else mapping.device_id
        _ensure_unique_mapping(db, endpoint_id, device_id, str(mapping_id))

    db.commit()
    db.refresh(mapping)
    return mapping


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(mapping_id: UUID, db: Session = Depends(get_db)):
    mapping = db.query(Mapping).filter(Mapping.id == str(mapping_id)).first()
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found.")

    db.delete(mapping)
    db.commit()
    return None
