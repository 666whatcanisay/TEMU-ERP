"""Shared record semantics; concrete adapters own SQL dialects and backups."""
from __future__ import annotations
import json
from datetime import datetime,timezone
from typing import Any
from ..domain import models

def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')

class RelationalStore:
    def check_health(self):
        try:
            return self._execute('SELECT 1').fetchone() is not None
        except Exception:
            return False

    # ---------- records ----------
    def upsert_record(self, record: dict[str, Any]) -> list[str]:
        errors = models.validate_record(record)
        if errors:
            return errors
        rtype = record["record_type"]
        rid = record.get("id")
        if not rid:
            if rtype == "policy":
                record["id"] = rid = "POLICY-CURRENT"
            else:
                return ["id: required"]
        now = _now()
        decision = record.get("internal_decision") if rtype == "candidate" else None
        market = record.get("research_market") if rtype == "candidate" else None
        candidate_id = record.get("candidate_id") if rtype == "feedback" else None
        synthetic = 1 if record.get("synthetic") else 0
        existing = self._execute(
            "SELECT created_at FROM records WHERE record_type=? AND id=?", (rtype, rid)
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        self._upsert('records',
            ['record_type','id','payload','decision','market','candidate_id','synthetic','created_at','updated_at'],
            [rtype,rid,json.dumps(record,ensure_ascii=False),decision,market,candidate_id,synthetic,created_at,now],
            ['record_type','id'], ['payload','decision','market','candidate_id','synthetic','updated_at'])
        self._commit()
        return []

    def get_record(self, rtype: str, rid: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT payload FROM records WHERE record_type=? AND id=?", (rtype, rid)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def record_metadata(self, rtype: str, rid: str) -> dict:
        row=self._execute('SELECT created_at,updated_at FROM records WHERE record_type=? AND id=?',(rtype,rid)).fetchone()
        return dict(row) if row else {}

    def list_records(self, rtype: str, candidate_id: str | None = None) -> list[dict[str, Any]]:
        if candidate_id:
            rows = self._execute(
                "SELECT payload FROM records WHERE record_type=? AND candidate_id=? ORDER BY updated_at DESC",
                (rtype, candidate_id),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT payload FROM records WHERE record_type=? ORDER BY updated_at DESC", (rtype,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def revision_history(self, candidate_id: str) -> list[dict[str, Any]]:
        rows = self._execute(
            "SELECT payload, created_at FROM revisions WHERE candidate_id=? ORDER BY created_at",
            (candidate_id,),
        ).fetchall()
        return [dict(json.loads(row["payload"]), created_at=row["created_at"]) for row in rows]

    def add_revision(self, candidate_id: str, sku_ref: str | None, field_key: str,
                     before: Any, after: Any, reviewer: str | None, method: str) -> None:
        payload = {
            "id": models.new_id("REV"),
            "candidate_id": candidate_id,
            "sku_ref": sku_ref,
            "field_key": field_key,
            "before": before,
            "after": after,
            "reviewer": reviewer,
            "extraction_method": method,
        }
        self._execute(
            "INSERT INTO revisions (id, candidate_id, sku_ref, field_key, payload, created_at) VALUES (?,?,?,?,?,?)",
            (payload["id"], candidate_id, sku_ref, field_key,
             json.dumps(payload, ensure_ascii=False), _now()),
        )
        self._commit()

    # ---------- adapter status ----------
    def set_adapter_status(self, port_key: str, status: str, detail: dict[str, Any]) -> None:
        self._upsert('adapter_status',['port_key','status','detail','updated_at'],
            [port_key,status,json.dumps(detail,ensure_ascii=False),_now()], ['port_key'], ['status','detail','updated_at'])
        self._commit()

    def adapter_statuses(self) -> dict[str, dict[str, Any]]:
        rows = self._execute("SELECT * FROM adapter_status").fetchall()
        return {
            row["port_key"]: {
                "status": row["status"],
                "detail": json.loads(row["detail"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        }

    # ---------- snapshots ----------
    def save_snapshot(self, source_id: str, snapshot_ref: str, sha256: str | None,
                      file_path: str | None, status: str, payload: dict[str, Any]) -> None:
        self._upsert('snapshots',['source_id','snapshot_ref','sha256','file_path','status','captured_at','payload'],
            [source_id,snapshot_ref,sha256,file_path,status,_now(),json.dumps(payload,ensure_ascii=False)],
            ['source_id'], ['snapshot_ref','sha256','file_path','status','captured_at','payload'])
        self._commit()

    def get_snapshot(self, source_id: str) -> dict[str, Any] | None:
        row = self._execute("SELECT * FROM snapshots WHERE source_id=?", (source_id,)).fetchone()
        if not row:
            return None
        return dict(json.loads(row["payload"]), status=row["status"], captured_at=row["captured_at"])

    # ---------- internal submissions ----------
    def save_submission(self, submission: dict[str, Any]) -> None:
        self._upsert('submissions',['id','candidate_id','payload','created_at'],
            [submission['id'],submission['candidate_id'],json.dumps(submission,ensure_ascii=False),submission['created_at']],
            ['id'], ['payload'])
        self._commit()

    def list_submissions(self, candidate_id: str | None = None) -> list[dict[str, Any]]:
        if candidate_id:
            rows = self._execute(
                "SELECT payload FROM submissions WHERE candidate_id=? ORDER BY created_at DESC",
                (candidate_id,),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT payload FROM submissions ORDER BY created_at DESC"
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

