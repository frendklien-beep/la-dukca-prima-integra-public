from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.domain.conversation import GenerationDiagnostics

logger = logging.getLogger("app.ai_diagnostics")

_SECRET_KEY = re.compile(
    r"(api[_-]?key|password|secret|token|cookie|authorization|session|prompt)", re.I
)
_NIK_OR_KK = re.compile(r"(?<!\d)\d{16}(?!\d)")
_LONG_DIGITS = re.compile(r"(?<!\d)\d{12,}(?!\d)")


def sanitize_diagnostic_value(value: Any, *, key: str = "") -> Any:
    if _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_diagnostic_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_diagnostic_value(item, key=key) for item in value]
    if isinstance(value, str):
        redacted = _NIK_OR_KK.sub("[REDACTED_ID]", value)
        redacted = _LONG_DIGITS.sub("[REDACTED_NUMBER]", redacted)
        return redacted[:1000]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:500]


@dataclass(slots=True)
class DiagnosticTrace:
    request_id: str
    enabled: bool
    started_at: float = field(default_factory=time.perf_counter)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    privacy: dict[str, Any] = field(
        default_factory=lambda: {"redaction_applied": False, "risk": "low"}
    )
    human_context: dict[str, Any] = field(default_factory=dict)
    intents: list[dict[str, Any]] = field(default_factory=list)
    clarification: dict[str, Any] = field(default_factory=dict)
    retrieval: dict[str, Any] = field(
        default_factory=lambda: {
            "queries": [],
            "documents_found": 0,
            "top_sources": [],
            "top_score": 0.0,
            "fallback_reason": None,
        }
    )
    regulatory_resolution: dict[str, Any] = field(
        default_factory=lambda: {
            "active_sources": [],
            "excluded_sources": [],
            "conflicts": [],
        }
    )
    service_plan: dict[str, Any] = field(default_factory=dict)
    openai: dict[str, Any] = field(
        default_factory=lambda: {
            "model": "",
            "prompt_version": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "attempts": 0,
        }
    )
    validation: dict[str, Any] = field(default_factory=dict)
    stage_duration_ms: dict[str, int] = field(default_factory=dict)
    _stage_started: dict[str, float] = field(default_factory=dict)

    def stage_start(self, name: str) -> None:
        if self.enabled:
            self._stage_started[name] = time.perf_counter()

    def stage_end(self, name: str) -> None:
        if not self.enabled:
            return
        started = self._stage_started.pop(name, None)
        if started is not None:
            self.stage_duration_ms[name] = int((time.perf_counter() - started) * 1000)

    def set_generation(self, diagnostics: GenerationDiagnostics | None) -> None:
        if diagnostics is None:
            return
        self.openai = {
            "model": diagnostics.model,
            "prompt_version": diagnostics.prompt_version,
            "input_tokens": diagnostics.input_tokens,
            "output_tokens": diagnostics.output_tokens,
            "attempts": diagnostics.attempts,
            "provider_request_id": diagnostics.provider_request_id,
        }

    def payload(self, result: str) -> dict[str, Any]:
        total_ms = int((time.perf_counter() - self.started_at) * 1000)
        value = {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "privacy": self.privacy,
            "human_context": self.human_context,
            "intents": self.intents,
            "clarification": self.clarification,
            "retrieval": self.retrieval,
            "regulatory_resolution": self.regulatory_resolution,
            "service_plan": self.service_plan,
            "openai": self.openai,
            "validation": self.validation,
            "performance": {
                "total_duration_ms": total_ms,
                "stage_duration_ms": self.stage_duration_ms,
            },
            "result": result,
        }
        return sanitize_diagnostic_value(value)

    def emit(self, result: str) -> None:
        if not self.enabled:
            return
        logger.info("ai_diagnostic %s", json.dumps(self.payload(result), ensure_ascii=False))
