"""Replaceable integration ports. Declaring a port does not implement a service."""
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Status = Literal["not_configured", "unavailable", "succeeded", "failed", "needs_review"]


@dataclass(frozen=True)
class AdapterResult:
    status: Status
    payload: dict[str, Any] = field(default_factory=dict)
    source_refs: tuple[str, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True)
class CollectRequest:
    task_id: str
    url: str
    allowed_hosts: tuple[str, ...]
    timeout_seconds: int = 30
    max_pages: int = 1


@dataclass(frozen=True)
class ExtractRequest:
    task_id: str
    snapshot_ref: str
    field_keys: tuple[str, ...]
    output_schema_version: str = "1.0"


class EvidenceCollector(Protocol):
    def collect(self, request: CollectRequest) -> AdapterResult: ...


class StructuredExtractor(Protocol):
    def extract(self, request: ExtractRequest) -> AdapterResult: ...


class CategoryTemplateProvider(Protocol):
    def get_template(self, shop_ref: str, category_id: str) -> AdapterResult: ...


class PlatformReadPort(Protocol):
    def read_status(self, shop_ref: str, platform_product_id: str) -> AdapterResult: ...


class SubmissionExporter(Protocol):
    def export(self, draft_ref: str, mapping_version: str, format_name: str) -> AdapterResult: ...


class RPAFillPlanPort(Protocol):
    def dry_run(self, draft_ref: str, page_version: str) -> AdapterResult: ...


class UnconfiguredExtractor:
    """The honest default for DSH/DeepSeek until a real adapter passes validation."""
    def extract(self, request: ExtractRequest) -> AdapterResult:
        return AdapterResult("not_configured", error_code="PROVIDER_NOT_CONFIGURED")
