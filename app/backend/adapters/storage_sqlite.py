"""SQLite storage adapter. Stdlib only; records are JSON payloads with index columns.

Long platform IDs stay in the JSON payload as original strings. The database is
the local source of truth: browser temporary state must not substitute for it.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..domain import models

SCHEMA_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                record_type TEXT NOT NULL,
                id TEXT NOT NULL,
                payload TEXT NOT NULL,
                decision TEXT,
                market TEXT,
                candidate_id TEXT,
                synthetic INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (record_type, id)
            );
            CREATE TABLE IF NOT EXISTS revisions (
                id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                sku_ref TEXT,
                field_key TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS adapter_status (
                port_key TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                detail TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                source_id TEXT PRIMARY KEY,
                snapshot_ref TEXT,
                sha256 TEXT,
                file_path TEXT,
                status TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

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
        existing = self._conn.execute(
            "SELECT created_at FROM records WHERE record_type=? AND id=?", (rtype, rid)
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        self._conn.execute(
            """INSERT INTO records
               (record_type, id, payload, decision, market, candidate_id, synthetic, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(record_type, id) DO UPDATE SET
                 payload=excluded.payload, decision=excluded.decision, market=excluded.market,
                 candidate_id=excluded.candidate_id, synthetic=excluded.synthetic, updated_at=excluded.updated_at""",
            (rtype, rid, json.dumps(record, ensure_ascii=False), decision, market,
             candidate_id, synthetic, created_at, now),
        )
        self._conn.commit()
        return []

    def get_record(self, rtype: str, rid: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload FROM records WHERE record_type=? AND id=?", (rtype, rid)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def record_metadata(self, rtype: str, rid: str) -> dict:
        row=self._conn.execute('SELECT created_at,updated_at FROM records WHERE record_type=? AND id=?',(rtype,rid)).fetchone()
        return dict(row) if row else {}

    def list_records(self, rtype: str, candidate_id: str | None = None) -> list[dict[str, Any]]:
        if candidate_id:
            rows = self._conn.execute(
                "SELECT payload FROM records WHERE record_type=? AND candidate_id=? ORDER BY updated_at DESC",
                (rtype, candidate_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM records WHERE record_type=? ORDER BY updated_at DESC", (rtype,)
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def revision_history(self, candidate_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
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
        self._conn.execute(
            "INSERT INTO revisions (id, candidate_id, sku_ref, field_key, payload, created_at) VALUES (?,?,?,?,?,?)",
            (payload["id"], candidate_id, sku_ref, field_key,
             json.dumps(payload, ensure_ascii=False), _now()),
        )
        self._conn.commit()

    # ---------- adapter status ----------
    def set_adapter_status(self, port_key: str, status: str, detail: dict[str, Any]) -> None:
        self._conn.execute(
            """INSERT INTO adapter_status (port_key, status, detail, updated_at) VALUES (?,?,?,?)
               ON CONFLICT(port_key) DO UPDATE SET status=excluded.status, detail=excluded.detail,
               updated_at=excluded.updated_at""",
            (port_key, status, json.dumps(detail, ensure_ascii=False), _now()),
        )
        self._conn.commit()

    def adapter_statuses(self) -> dict[str, dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM adapter_status").fetchall()
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
        self._conn.execute(
            """INSERT INTO snapshots (source_id, snapshot_ref, sha256, file_path, status, captured_at, payload)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(source_id) DO UPDATE SET snapshot_ref=excluded.snapshot_ref,
                 sha256=excluded.sha256, file_path=excluded.file_path, status=excluded.status,
                 captured_at=excluded.captured_at, payload=excluded.payload""",
            (source_id, snapshot_ref, sha256, file_path, status, _now(),
             json.dumps(payload, ensure_ascii=False)),
        )
        self._conn.commit()

    def get_snapshot(self, source_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM snapshots WHERE source_id=?", (source_id,)).fetchone()
        if not row:
            return None
        return dict(json.loads(row["payload"]), status=row["status"], captured_at=row["captured_at"])

    # ---------- internal submissions ----------
    def save_submission(self, submission: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO submissions (id, candidate_id, payload, created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
            (submission["id"], submission["candidate_id"],
             json.dumps(submission, ensure_ascii=False), submission["created_at"]),
        )
        self._conn.commit()

    def list_submissions(self, candidate_id: str | None = None) -> list[dict[str, Any]]:
        if candidate_id:
            rows = self._conn.execute(
                "SELECT payload FROM submissions WHERE candidate_id=? ORDER BY created_at DESC",
                (candidate_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM submissions ORDER BY created_at DESC"
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    # ---------- backup / restore ----------
    def backup(self, target_path: str | Path) -> Path:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._conn.commit()
        with sqlite3.connect(str(target)) as destination:
            self._conn.backup(destination)
        return target

    def restore(self, source_path: str | Path) -> list[str]:
        source = Path(source_path)
        if not source.is_file():
            return ["backup file not found"]
        try:
            with sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro', uri=True) as saved:
                if saved.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    return ['backup database integrity check failed']
                required = {'records','revisions','submissions','snapshots','adapter_status'}
                tables = {r[0] for r in saved.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not required.issubset(tables):
                    return ['not a workbench backup database']
                saved.backup(self._conn)
        except sqlite3.DatabaseError:
            return ['invalid backup database']
        return []

    def close(self) -> None:
        self._conn.close()
