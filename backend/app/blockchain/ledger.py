"""
Local test blockchain ledger.
Implements hash-chained block storage without real cryptocurrency.
Only stores evidence IDs and SHA-256 hashes — never actual images.
Configurable to swap in Web3/Polygon via BLOCKCHAIN_MODE env var.
"""
import json
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from threading import Lock

from app.config import settings

_lock = Lock()  # Thread safety for file writes


class LocalTestLedger:
    """
    File-backed local blockchain for development and testing.
    - SHA-256 block hash chaining (each block references previous block hash)
    - Append-only (no delete, no update)
    - Evidence hash stored, image NEVER stored
    - Works without Ethereum, gas fees, or wallets
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, ledger_path: Optional[str] = None):
        self.path = Path(ledger_path or settings.LOCAL_LEDGER_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_genesis()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists() and self.path.stat().st_size > 0:
            try:
                with open(self.path, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return {"chain": [], "index": {}}

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _ensure_genesis(self) -> None:
        with _lock:
            data = self._load()
            if not data["chain"]:
                genesis = self._make_block(
                    evidence_id="GENESIS",
                    image_hash=self.GENESIS_HASH,
                    previous_hash=self.GENESIS_HASH,
                    block_number=0,
                )
                data["chain"].append(genesis)
                self._save(data)

    def _compute_block_hash(self, block: Dict[str, Any]) -> str:
        payload = (
            f"{block['block_number']}"
            f"{block['evidence_id']}"
            f"{block['image_hash']}"
            f"{block['timestamp']}"
            f"{block['previous_hash']}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _make_block(
        self,
        evidence_id: str,
        image_hash: str,
        previous_hash: str,
        block_number: int,
    ) -> Dict[str, Any]:
        tx_id = f"0x{uuid.uuid4().hex}"
        block = {
            "block_number": block_number,
            "transaction_id": tx_id,
            "evidence_id": evidence_id,
            "image_hash": image_hash,
            "previous_hash": previous_hash,
            "timestamp": datetime.utcnow().isoformat(),
            "chain_id": "local-testnet-001",
            "provider": "local",
        }
        block["block_hash"] = self._compute_block_hash(block)
        return block

    def register_hash(self, evidence_id: str, image_hash: str) -> Dict[str, Any]:
        """Register an evidence hash on the local chain. Returns transaction details."""
        with _lock:
            data = self._load()

            # Check for duplicate
            if evidence_id in data.get("index", {}):
                existing_block_num = data["index"][evidence_id]
                existing_block = data["chain"][existing_block_num]
                return {**existing_block, "already_registered": True}

            previous_hash = data["chain"][-1]["block_hash"] if data["chain"] else self.GENESIS_HASH
            block_number = len(data["chain"])
            block = self._make_block(evidence_id, image_hash, previous_hash, block_number)

            data["chain"].append(block)
            data.setdefault("index", {})[evidence_id] = block_number
            self._save(data)

            return {**block, "already_registered": False}

    def verify_hash(self, evidence_id: str, image_hash: str) -> Dict[str, Any]:
        """
        Verify that the given hash matches what was registered on-chain.
        Returns verification result with tamper detection.
        """
        with _lock:
            data = self._load()
            index = data.get("index", {})

            if evidence_id not in index:
                return {
                    "is_valid": False,
                    "registered": False,
                    "message": "Evidence hash not found on blockchain",
                    "evidence_id": evidence_id,
                }

            block_num = index[evidence_id]
            block = data["chain"][block_num]

            registered_hash = block["image_hash"]
            hashes_match = registered_hash == image_hash

            # Also verify block hash integrity
            recomputed = self._compute_block_hash(block)
            block_intact = recomputed == block["block_hash"]

            return {
                "is_valid": hashes_match and block_intact,
                "registered": True,
                "registered_hash": registered_hash,
                "current_hash": image_hash,
                "transaction_id": block["transaction_id"],
                "block_number": block["block_number"],
                "block_hash": block["block_hash"],
                "chain_id": block["chain_id"],
                "registered_at": block["timestamp"],
                "block_intact": block_intact,
                "message": (
                    "Hash verified — evidence integrity confirmed on local testnet"
                    if hashes_match and block_intact
                    else "INTEGRITY MISMATCH — registered hash differs from current hash"
                ),
            }

    def get_chain_length(self) -> int:
        data = self._load()
        return len(data["chain"])

    def get_block(self, block_number: int) -> Optional[Dict[str, Any]]:
        data = self._load()
        chain = data["chain"]
        if 0 <= block_number < len(chain):
            return chain[block_number]
        return None


# ─── Factory ──────────────────────────────────────────────────────────────────

def get_blockchain_provider():
    """Return the configured blockchain provider."""
    mode = settings.BLOCKCHAIN_MODE.lower()
    if mode == "local":
        return LocalTestLedger()
    # Future: elif mode == "ethereum": return EthereumProvider()
    raise ValueError(f"Unsupported blockchain mode: {mode}")


blockchain = get_blockchain_provider()
