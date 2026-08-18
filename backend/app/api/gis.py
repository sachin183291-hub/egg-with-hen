"""GIS API — evidence markers for Leaflet map."""
from typing import Optional, List
from datetime import datetime
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import User, Evidence, EvidenceMetadata, AIVerification, BlockchainRecord, EvidenceStatusEnum
from app.schemas.schemas import GISMarkerResponse
from app.security.rbac import get_current_user

router = APIRouter(prefix="/api/gis", tags=["GIS"])


@router.get("/evidence", response_model=List[GISMarkerResponse])
async def get_gis_evidence(
    status: Optional[EvidenceStatusEnum] = Query(None),
    user_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all evidence records with GPS coordinates for the map."""
    q = (
        db.query(Evidence, EvidenceMetadata, AIVerification, BlockchainRecord, User)
        .join(EvidenceMetadata, EvidenceMetadata.evidence_id == Evidence.id, isouter=True)
        .join(AIVerification, AIVerification.evidence_id == Evidence.id, isouter=True)
        .join(BlockchainRecord, BlockchainRecord.evidence_id == Evidence.id, isouter=True)
        .join(User, User.id == Evidence.user_id)
        .filter(Evidence.deleted_at == None)
        .filter(EvidenceMetadata.latitude != None)
    )

    if status:
        q = q.filter(Evidence.status == status)
    if user_id:
        q = q.filter(Evidence.user_id == user_id)
    if date_from:
        q = q.filter(Evidence.created_at >= date_from)
    if date_to:
        q = q.filter(Evidence.created_at <= date_to)

    results = q.limit(500).all()  # Cap for performance

    markers = []
    for ev, meta, ai, bc, user in results:
        if meta and meta.latitude and meta.longitude:
            markers.append(GISMarkerResponse(
                evidence_id=ev.id,
                evidence_number=ev.evidence_number,
                latitude=meta.latitude,
                longitude=meta.longitude,
                status=ev.status,
                capture_timestamp=meta.capture_timestamp,
                officer_name=user.full_name,
                ai_status=ai.status if ai else None,
                ai_confidence=ai.confidence_score if ai else None,
                blockchain_status=bc.status if bc else None,
                thumbnail_url=ev.thumbnail_url,
            ))

    return markers


@router.get("/locations")
async def get_locations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return unique location clusters for the map overview."""
    metas = db.query(EvidenceMetadata).limit(500).all()
    return {
        "count": len(metas),
        "locations": [
            {"lat": m.latitude, "lon": m.longitude, "evidence_id": m.evidence_id}
            for m in metas if m.latitude and m.longitude
        ]
    }
