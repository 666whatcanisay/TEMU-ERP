"""Local HTTP API + static file server. Stdlib only; no framework dependency.

The browser UI calls these endpoints. Domain rules live in the service layer;
this layer only parses requests, validates payload shape and serializes responses.
"""
from __future__ import annotations

import json
import mimetypes
import os
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .. import config
from ..factory import build_service

STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "static"
SERVICE = build_service()


class Handler(BaseHTTPRequestHandler):
    server_version = "temu-workbench/1.0"

    # ---------- helpers ----------
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            self._send_json({"error": f"invalid JSON: {exc}"}, 400)
            return {}

    def _route(self, path: str):
        return [p for p in path.split("/") if p]

    def log_message(self, fmt: str, *args) -> None:
        print(f"[api] {self.address_string()} {fmt % args}", flush=True)

    # ---------- GET ----------
    def do_GET(self) -> None:
        try:
            self._get()
        except Exception:
            traceback.print_exc()
            self._send_json({"error": "internal error", "detail": traceback.format_exc()[-1000:]}, 500)

    def _get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        parts = self._route(path)
        documents={
            '/database':config.ROOT/'docs/DATABASE_TOUR.html',
            '/assets/database-er.svg':config.ROOT/'docs/assets/database-er.svg',
            '/database/interview-queries.sql':config.ROOT/'database/interview-queries.sql',
            '/database/migrations/002_relational_entities.sql':config.ROOT/'database/migrations/002_relational_entities.sql',
        }
        if path in documents:
            return self._file(documents[path])
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if parts and parts[0] == "static":
            return self._static("/".join(parts[1:]))
        if path == "/api/health":
            ok = SERVICE.store.check_health()
            return self._send_json({"ok": ok, "mode": config.MODE,
                                    "database":{**config.database_info(),"schema_version":getattr(SERVICE.store,'schema_version','sqlite-v1')},
                                    "live_write_enabled": config.LIVE_WRITE_ENABLED},200 if ok else 503)
        if path == "/api/meta":
            return self._send_json(SERVICE.registry())
        if path == "/api/candidates":
            return self._send_json({"candidates": SERVICE.list_candidates()})
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "candidates":
            detail = SERVICE.get_candidate(parts[2])
            if detail is None:
                return self._send_json({"error": "not found"}, 404)
            return self._send_json(detail)
        if path == "/api/sources":
            return self._send_json({"sources": SERVICE.list_sources()})
        if path == "/api/policy":
            return self._send_json({"policy": SERVICE.get_policy()})
        if path == "/api/export":
            fmt = parse_qs(parsed.query).get("format", ["json"])[0]
            if fmt not in ("json", "csv"):
                return self._send_json({"error": "format must be json or csv"}, 400)
            bundle = SERVICE.export_bundle(fmt)
            return self._send_json(bundle)
        if path == "/api/backups":
            return self._send_json({"backups": self._list_backups()})
        return self._send_json({"error": "not found"}, 404)

    def _static(self, rel: str) -> None:
        candidate = (STATIC_DIR / rel).resolve()
        if not candidate.is_relative_to(STATIC_DIR.resolve()) or not candidate.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        return self._file(candidate)

    def _file(self,candidate: Path) -> None:
        if not candidate.is_file():
            return self._send_json({'error':'not found'},404)
        ctype, _ = mimetypes.guess_type(str(candidate))
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---------- POST ----------
    def do_POST(self) -> None:
        try:
            self._post()
        except Exception:
            traceback.print_exc()
            try:
                self._send_json({"error": "internal error", "detail": traceback.format_exc()[-1000:]}, 500)
            except Exception:
                pass

    def _post(self) -> None:
        parts = self._route(urlparse(self.path).path)
        body = self._read_json()

        if len(parts) == 2 and parts == ["api", "candidates"]:
            errors = SERVICE.save_candidate(body)
            return self._send_json({"errors": errors}, 200 if not errors else 400)
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "candidates" and parts[3] == "decision":
            errors = SERVICE.set_decision(parts[2], body.get("decision", ""),
                                          body.get("reason", ""), body.get("reviewer"))
            return self._send_json({"errors": errors}, 200 if not errors else 400)
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "candidates" and parts[3] == "restore":
            errors = SERVICE.restore_decision(parts[2], body.get("reviewer"))
            return self._send_json({"errors": errors}, 200 if not errors else 400)
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "candidates" and parts[3] == "feedback":
            result = SERVICE.add_feedback(body)
            return self._send_json(result, 200 if result["status"] == "succeeded" else 400)
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "candidates" and parts[3] == "submission":
            result = SERVICE.build_submission(parts[2])
            return self._send_json(result, 200 if result["status"] == "succeeded" else 400)
        if len(parts) == 2 and parts == ["api", "sources"]:
            errors = SERVICE.save_source(body)
            return self._send_json({"errors": errors, "id": body.get("id")}, 200 if not errors else 400)
        if len(parts) == 2 and parts == ["api", "import"]:
            report = SERVICE.import_bundle(body.get("format", "json"), body.get("content", ""))
            return self._send_json({"report": report})
        if len(parts) == 2 and parts == ["api", "collect"]:
            result = SERVICE.collect_page(body.get('task_id','manual'),body.get('url',''),config.COLLECT_ALLOWED_HOSTS,body.get('candidate_id'))
            return self._send_json({"status": result.status, "payload": result.payload,
                                    "error_code": result.error_code})
        if len(parts) == 2 and parts == ["api", "backup"]:
            path = self._backup_path()
            SERVICE.backup(path)
            return self._send_json({"backup": path.name})
        if len(parts) == 2 and parts == ["api", "restore"]:
            filename = body.get('filename')
            if not isinstance(filename,str) or Path(filename).name != filename or not filename.endswith(SERVICE.store.backup_suffix):
                return self._send_json({'errors':['请选择当前数据库类型的有效备份文件']},400)
            errors = SERVICE.restore(str(self._backup_dir() / filename))
            return self._send_json({"errors": errors}, 200 if not errors else 400)
        return self._send_json({"error": "not found"}, 404)

    def do_PUT(self) -> None:
        try:
            self._put()
        except Exception:
            traceback.print_exc()
            self._send_json({"error": "internal error", "detail": traceback.format_exc()[-1000:]}, 500)

    def _put(self) -> None:
        parts = self._route(urlparse(self.path).path)
        body = self._read_json()
        if len(parts) == 2 and parts == ["api", "policy"]:
            errors = SERVICE.save_policy(body)
            return self._send_json({"errors": errors}, 200 if not errors else 400)
        return self._send_json({"error": "not found"}, 404)

    # ---------- backups ----------
    def _backup_dir(self) -> Path:
        directory = config.DATA_DIR / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _backup_path(self) -> Path:
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return self._backup_dir() / f"workbench-backup-{stamp}{SERVICE.store.backup_suffix}"

    def _list_backups(self) -> list[dict]:
        return [{"filename": p.name, "bytes": p.stat().st_size,
                 "modified": p.stat().st_mtime}
                for p in sorted(self._backup_dir().glob('*'+SERVICE.store.backup_suffix), reverse=True)]


def main() -> None:
    # Keep this single-user HTTP service serialized across storage and backup operations.
    server = HTTPServer((config.HOST, config.PORT), Handler)
    print(f"Temu 选品提报工作台已启动: http://{config.HOST}:{config.PORT}")
    print("退出方式: 在本窗口按 Ctrl+C。数据库:", SERVICE.store.engine, SERVICE.store.location)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止服务…")
    finally:
        server.server_close()
        SERVICE.store.close()


if __name__ == "__main__":
    main()
