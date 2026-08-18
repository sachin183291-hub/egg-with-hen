"""Blockchain API — register and verify evidence hashes."""
from datetime import datetime
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import User, Evidence, BlockchainRecord, AuditActionEnum, BlockchainStatusEnum
from app.schemas.schemas import BlockchainRegisterResponse, BlockchainVerifyResponse
from app.security.rbac import get_current_user, require_admin_or_above
from app.blockchain.ledger import blockchain
from app.services.audit import log_action

router = APIRouter(prefix="/api/blockchain", tags=["Blockchain"])


@router.post("/register/{evidence_id}", response_model=BlockchainRegisterResponse)
async def register_evidence_hash(
    evidence_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register the evidence image hash on the blockchain/test ledger."""
    ev = db.query(Evidence).filter(Evidence.id == evidence_id, Evidence.deleted_at == None).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    bc_record = db.query(BlockchainRecord).filter(BlockchainRecord.evidence_id == evidence_id).first()

    # Register on chain
    try:
        result = blockchain.register_hash(evidence_id, ev.image_sha256_hash)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Blockchain registration failed: {e}")

    # Update DB record
    if bc_record:
        bc_record.transaction_id = result["transaction_id"]
        bc_record.block_number = result["block_number"]
        bc_record.block_hash = result["block_hash"]
        bc_record.chain_id = result.get("chain_id", "local")
        bc_record.status = BlockchainStatusEnum.REGISTERED
        bc_record.registered_at = datetime.utcnow()
    else:
        bc_record = BlockchainRecord(
            evidence_id=evidence_id,
            image_hash=ev.image_sha256_hash,
            transaction_id=result["transaction_id"],
            block_number=result["block_number"],
            block_hash=result["block_hash"],
            chain_id=result.get("chain_id", "local"),
            provider="local",
            status=BlockchainStatusEnum.REGISTERED,
            registered_at=datetime.utcnow(),
        )
        db.add(bc_record)

    log_action(
        db, AuditActionEnum.BLOCKCHAIN_REGISTERED,
        user_id=current_user.id, resource_type="blockchain", resource_id=evidence_id,
        description=f"Hash registered on blockchain: tx={result['transaction_id']}",
        result="SUCCESS", request=request,
    )
    db.commit()

    return BlockchainRegisterResponse(
        transaction_id=result["transaction_id"],
        block_number=result["block_number"],
        block_hash=result["block_hash"],
        evidence_id=evidence_id,
        image_hash=ev.image_sha256_hash,
        registered_at=bc_record.registered_at,
        provider="local",
    )


@router.get("/verify/{evidence_id}", response_model=BlockchainVerifyResponse)
async def verify_evidence_hash(
    evidence_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify that the evidence hash matches the blockchain record."""
    ev = db.query(Evidence).filter(Evidence.id == evidence_id, Evidence.deleted_at == None).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    bc_record = db.query(BlockchainRecord).filter(BlockchainRecord.evidence_id == evidence_id).first()
    if not bc_record or bc_record.status == BlockchainStatusEnum.NOT_REGISTERED:
        raise HTTPException(status_code=404, detail="Evidence not yet registered on blockchain")

    try:
        result = blockchain.verify_hash(evidence_id, ev.image_sha256_hash)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Blockchain verification failed: {e}")

    # Update verification count and status
    bc_record.verification_count = (bc_record.verification_count or 0) + 1
    bc_record.last_verified_at = datetime.utcnow()
    if not result["is_valid"]:
        bc_record.status = BlockchainStatusEnum.MISMATCH

    log_action(
        db, AuditActionEnum.BLOCKCHAIN_VERIFIED,
        user_id=current_user.id, resource_type="blockchain", resource_id=evidence_id,
        description=f"Blockchain verification: {'VALID' if result['is_valid'] else 'MISMATCH'}",
        result="SUCCESS" if result["is_valid"] else "FAILED", request=request,
    )
    db.commit()

    return BlockchainVerifyResponse(
        is_valid=result["is_valid"],
        evidence_id=evidence_id,
        registered_hash=result.get("registered_hash", ""),
        current_hash=ev.image_sha256_hash,
        transaction_id=result.get("transaction_id"),
        block_number=result.get("block_number"),
        provider="local",
        verified_at=datetime.utcnow(),
    )
