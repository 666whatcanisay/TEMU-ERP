"""SQLite storage adapter. Stdlib only; records are JSON payloads with index columns.

Long platform IDs stay in the JSON payload as original strings. The database is
the local source of truth: browser temporary state must not substitute for it.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from .storage_relational import RelationalStore

SCHEMA_VERSION = "1.0"


class SQLiteStore(RelationalStore):
    engine = 'sqlite'
    backup_suffix = '.db'
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._in_transaction = False
        self._init_schema()

    @property
    def location(self):
        return str(self.db_path)

    def _execute(self, sql, params=()):
        return self._conn.execute(sql, params)

    def _commit(self):
        if not self._in_transaction:
            self._conn.commit()

    @contextmanager
    def transaction(self):
        if self._in_transaction:
            raise RuntimeError('Nested database transaction is not supported')
        self._conn.execute('BEGIN IMMEDIATE')
        self._in_transaction = True
        try:
            yield
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise
        finally:
            self._in_transaction = False

    def _upsert(self, table, columns, values, keys, updates):
        names=','.join(columns)
        marks=','.join('?' for _ in columns)
        change=','.join(f'{key}=excluded.{key}' for key in updates)
        self._execute(f'INSERT INTO {table} ({names}) VALUES ({marks}) ON CONFLICT({",".join(keys)}) DO UPDATE SET {change}',values)

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

    # ---------- backup / restore ----------
    def export_state(self):
        from . import storage_state
        if self._conn.in_transaction:
            raise RuntimeError('Cannot export a partial SQLite transaction')
        self._conn.execute('BEGIN')
        try:
            tables={t:[dict(row) for row in self._conn.execute(f'SELECT * FROM {t}').fetchall()]
                    for t in storage_state.TABLES}
            return storage_state.envelope(tables)
        finally:
            self._conn.rollback()

    def backup(self, target_path: str | Path) -> Path:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._conn.commit()
        with closing(sqlite3.connect(str(target))) as destination:
            self._conn.backup(destination)
        return target

    def restore(self, source_path: str | Path) -> list[str]:
        source = Path(source_path)
        if not source.is_file():
            return ["backup file not found"]
        try:
            with closing(sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro', uri=True)) as saved:
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
