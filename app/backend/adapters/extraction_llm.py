"""DSH and DeepSeek adapters: separate ports, honest unconfigured/unavailable states.

No credential file is read or copied. A missing key means ``not_configured``;
an unreachable or unauthorized service means ``unavailable`` after one attempt.
Model output always arrives as source-backed field candidates, never as confirmed
product fields or platform policy.
"""
from __future__ import annotations

import os
from typing import Any

from ..domain.ports import AdapterResult, ExtractRequest


class DeepSeekApiExtractor:
    name = "deepseek_api"

    def __init__(self) -> None:
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "").strip()
        self.model = os.environ.get("DEEPSEEK_MODEL", "").strip()

    def status(self) -> dict[str, Any]:
        if not self.api_key:
            return {"status": "not_configured", "error_code": "NO_API_KEY",
                    "detail": "DEEPSEEK_API_KEY 未配置；本地录入与计算不受影响。"}
        return {"status": "unavailable", "error_code": "NOT_IMPLEMENTED",
                "detail": "已检测到密钥，但本轮未实现真实联网提取；不得在界面显示连接成功。"}

    def extract(self, request: ExtractRequest) -> AdapterResult:
        if not self.api_key:
            return AdapterResult("not_configured", error_code="NO_API_KEY")
        return AdapterResult("unavailable", error_code="NOT_IMPLEMENTED")


class DSHExtractor:
    name = "dsh"

    def __init__(self) -> None:
        self.base_url = os.environ.get("DSH_BASE_URL", "").strip()
        try:
            self.max_tasks = int(os.environ.get("DSH_MAX_TASKS", "6"))
        except ValueError:
            self.max_tasks = 6

    def status(self) -> dict[str, Any]:
        if not self.base_url:
            return {"status": "not_configured", "error_code": "NO_DSH_BASE_URL",
                    "detail": "未配置 DSH 本地入口地址；未读取凭据文件，未改动原 profile。"}
        return {"status": "unavailable", "error_code": "NOT_IMPLEMENTED",
                "detail": "检测到入口配置，本轮未完成真实联调。"}

    def extract(self, request: ExtractRequest) -> AdapterResult:
        if not self.base_url:
            return AdapterResult("not_configured", error_code="NO_DSH_BASE_URL")
        return AdapterResult("unavailable", error_code="NOT_IMPLEMENTED")
