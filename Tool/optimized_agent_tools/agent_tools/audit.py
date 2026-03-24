from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json

from .types import AuditRecord, ToolResult, new_audit_id, sha256_text, stable_json_dumps


class AuditLogger:
    def __init__(self, log_path: str | Path) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._load_last_hash()

    def _load_last_hash(self) -> str | None:
        if not self.log_path.exists():
            return None
        last = None
        with self.log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                last = item.get("chain_hash") or last
        return last

    def write(self, *, session_id: str, tool: str, decision: str, payload: dict, result: ToolResult, notes: list[str] | None = None) -> AuditRecord:
        audit_id = new_audit_id()
        payload_hash = sha256_text(stable_json_dumps(payload))
        result_hash = sha256_text(stable_json_dumps(result.data))
        chain_input = stable_json_dumps(
            {
                "audit_id": audit_id,
                "session_id": session_id,
                "tool": tool,
                "decision": decision,
                "payload_sha256": payload_hash,
                "result_sha256": result_hash,
                "prev_hash": self._last_hash,
            }
        )
        chain_hash = sha256_text(chain_input)
        record = AuditRecord(
            audit_id=audit_id,
            timestamp=result.data.get("timestamp", ""),
            session_id=session_id,
            tool=tool,
            decision=decision,
            payload_sha256=payload_hash,
            result_sha256=result_hash,
            prev_hash=self._last_hash,
            chain_hash=chain_hash,
            notes=list(notes or []),
        )
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        self._last_hash = chain_hash
        return record
