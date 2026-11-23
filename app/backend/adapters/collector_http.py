"""Stdlib HTTP evidence collector: small-sample only, host-limited, one retry.

Public, read-only pages only. A blocked or unreachable page keeps failure
evidence and a manual entry; we never fill missing content from a model.
"""
from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..domain.ports import AdapterResult, CollectRequest


class HttpEvidenceCollector:
    def __init__(self, cache_dir: Path, user_agent: str = "temu-workbench-local/1.0"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent

    def collect(self, request: CollectRequest) -> AdapterResult:
        parsed = urlparse(request.url)
        host = parsed.netloc.lower()
        if parsed.scheme not in ('http', 'https'):
            return AdapterResult("failed", error_code="BAD_URL", payload={"url": request.url})
        allowed = [h.lower() for h in (request.allowed_hosts or ())]
        if not allowed or host not in allowed:
            return AdapterResult("failed", error_code="HOST_NOT_ALLOWED",
                                  payload={"url": request.url, "host": host,
                                           "allowed_hosts": allowed})

        body: bytes | None = None
        last_error: str | None = None
        for attempt in (1, 2):  # one retry counts toward the two-attempt limit
            try:
                req = urllib.request.Request(
                    request.url,
                    headers={"User-Agent": self.user_agent, "Accept-Language": "de,en;q=0.8"},
                )
                with urllib.request.urlopen(req, timeout=request.timeout_seconds) as resp:
                    final_host = urlparse(resp.geturl()).netloc.lower()
                    if final_host not in allowed:
                        return AdapterResult('failed', error_code='REDIRECT_HOST_NOT_ALLOWED')
                    body = resp.read(2_000_001)
                    status = resp.status
                    content_type = resp.headers.get("Content-Type", "")
                last_error = None
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        if body is None:
            return AdapterResult(
                "failed",
                error_code="FETCH_FAILED",
                payload={"url": request.url, "attempts": 2, "error": last_error,
                         "manual_entry_available": True},
            )

        sha = hashlib.sha256(body).hexdigest()
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", host)[:40]
        snapshot_ref = f"snap-{request.task_id}-{safe}"
        file_path = self.cache_dir / f"{snapshot_ref}.html"
        file_path.write_bytes(body)
        text = body.decode("utf-8", errors="replace")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        title = re.sub(r"\s+", " ", title_match.group(1)).strip()[:200] if title_match else None
        return AdapterResult(
            "succeeded",
            payload={
                "url": request.url,
                "host": host,
                "http_status": status,
                "content_type": content_type,
                "bytes": len(body),
                'truncated':len(body)>2_000_000,
                "sha256": sha,
                "snapshot_ref": snapshot_ref,
                "file_path": str(file_path),
                "title": title,
                "captured_at": None,  # filled by service layer with local ISO time
            },
            source_refs=(request.url,),
        )
