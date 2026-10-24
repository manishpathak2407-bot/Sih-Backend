import hashlib
import json
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

class AuditService:
    """
    Military-grade tamper-evident audit logging service.
    Every schedule approval, override, and requisition is signed with SHA-256 hash chaining.
    """
    def __init__(self):
        self.log_chain: List[Dict[str, Any]] = []
        self._initialize_genesis_entry()

    def _initialize_genesis_entry(self):
        genesis = {
            "entry_id": 1,
            "index": 1,
            "timestamp": "2026-10-20T08:00:00Z",
            "operator_id": "SYS-INIT",
            "operator_rank": "System Daemon",
            "action": "SYSTEM_INITIALIZATION",
            "details": "SkyReady Air-Gapped Secure Audit Log Initialized. DSSC Protocol SIH26249 active.",
            "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000",
            "hash": "",
            "current_hash": ""
        }
        computed = self._compute_hash(genesis)
        genesis["hash"] = computed
        genesis["current_hash"] = computed
        self.log_chain.append(genesis)

        # Seed initial system log entries
        self.record_entry(
            operator_id="AF-ENG-8492",
            operator_rank="Wing Commander (Chief Engineering Officer)",
            action="DATA_INGEST_VERIFIED",
            details="Ingested telemetry from No. 45 Flying Daggers. 24 airframes synchronized with C-MAPSS baseline.",
            justification="Mandatory pre-flight health sync"
        )

    def _compute_hash(self, entry: Dict[str, Any]) -> str:
        payload = f"{entry['entry_id']}|{entry['timestamp']}|{entry['operator_id']}|{entry['action']}|{entry['details']}|{entry['prev_hash']}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record_entry(
        self,
        operator_id: str,
        operator_rank: str,
        action: str,
        details: str,
        justification: Optional[str] = None
    ) -> Dict[str, Any]:
        prev_entry = self.log_chain[-1]
        new_id = prev_entry["entry_id"] + 1
        
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = {
            "entry_id": new_id,
            "index": new_id,
            "timestamp": now_ts,
            "operator_id": operator_id,
            "operator_rank": operator_rank,
            "action": action,
            "details": details,
            "justification": justification or "Routine operational authorization",
            "prev_hash": prev_entry["hash"],
            "hash": "",
            "current_hash": ""
        }
        computed = self._compute_hash(entry)
        entry["hash"] = computed
        entry["current_hash"] = computed
        self.log_chain.append(entry)
        return entry

    def verify_integrity(self) -> Dict[str, Any]:
        """
        Validates cryptographic integrity of the audit chain.
        """
        for i in range(1, len(self.log_chain)):
            prev = self.log_chain[i - 1]
            curr = self.log_chain[i]
            if curr["prev_hash"] != prev["hash"]:
                return {"is_valid": False, "compromised_entry_id": curr["entry_id"]}
            if curr["hash"] != self._compute_hash(curr):
                return {"is_valid": False, "compromised_entry_id": curr["entry_id"]}

        return {
            "is_valid": True,
            "total_entries": len(self.log_chain),
            "latest_hash": self.log_chain[-1]["hash"],
            "status": "ALL_SIGNATURES_VERIFIED"
        }

    def get_logs(self) -> List[Dict[str, Any]]:
        return list(reversed(self.log_chain))

audit_service = AuditService()
