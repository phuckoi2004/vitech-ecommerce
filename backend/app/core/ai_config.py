"""Lazy AI configuration; a missing key never prevents the shop from starting."""

import math
import os
from dataclasses import dataclass, field
from functools import lru_cache

from app.services.exceptions import AiUnavailableError

from .env import load_environment


@dataclass(frozen=True)
class AiSettings:
    api_key: str = field(default="", repr=False)
    model: str = "gemini-3.5-flash-lite"
    fallback_model: str = "gemini-3.8-flash"  # Reserved; no automatic model retries.
    timeout_seconds: float = 60
    input_max_chars: int = 1000
    context_max_turns: int = 12
    max_output_tokens: int = 2048
    benchmark_tokens_per_minute: int = 0  # Set to the actual AI Studio project limit; 0 disables pacing.
    requests_per_minute: int = 10
    max_attempts: int = 3
    max_tool_rounds: int = 4
    max_products: int = 3
    ranking_enabled: bool = True  # Stage 10.6; false gives the baseline catalog order for evaluation.

    def __post_init__(self):
        if (not self.model.strip() or not self.model.startswith("gemini-")
                or (self.fallback_model and not self.fallback_model.startswith("gemini-"))
                or not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 120
                or not 1 <= self.input_max_chars <= 1000 or not 1 <= self.context_max_turns <= 12
                or not 1 <= self.max_output_tokens <= 8192
                or not 0 <= self.benchmark_tokens_per_minute <= 10**9
                or not 1 <= self.requests_per_minute <= 60 or not 1 <= self.max_attempts <= 10
                or not 1 <= self.max_tool_rounds <= 4 or not 1 <= self.max_products <= 3):
            raise AiUnavailableError("Cấu hình AI không hợp lệ", code="ai_invalid_configuration")

    @property
    def lease_seconds(self) -> int:
        return max(120, math.ceil(self.timeout_seconds * 3))


def _flag(value: str) -> bool:
    value = value.strip().lower()
    if value not in {"true", "false", "1", "0"}:
        raise ValueError("Expected true/false")
    return value in {"true", "1"}


@lru_cache(maxsize=1)
def get_ai_settings() -> AiSettings:
    load_environment()
    try:
        return AiSettings(
            api_key=(os.getenv("GEMINI_API_KEY") or "").strip(),
            model=(os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite").strip(),
            fallback_model=(os.getenv("GEMINI_FALLBACK_MODEL") or "gemini-3.8-flash").strip(),
            timeout_seconds=float(os.getenv("AI_TIMEOUT_SECONDS", "60")),
            input_max_chars=int(os.getenv("AI_INPUT_MAX_CHARS", "1000")),
            context_max_turns=int(os.getenv("AI_CONTEXT_MAX_TURNS", "12")),
            max_output_tokens=int(os.getenv("AI_MAX_OUTPUT_TOKENS", "2048")),
            benchmark_tokens_per_minute=int(os.getenv("AI_BENCHMARK_TOKENS_PER_MINUTE", "0")),
            requests_per_minute=int(os.getenv("AI_REQUESTS_PER_MINUTE", "10")),
            max_attempts=int(os.getenv("AI_MAX_ATTEMPTS", "3")),
            max_tool_rounds=int(os.getenv("AI_MAX_TOOL_ROUNDS", "4")),
            max_products=int(os.getenv("AI_MAX_PRODUCTS", "3")),
            ranking_enabled=_flag(os.getenv("AI_RANKING_ENABLED", "true")),
        )
    except (TypeError, ValueError, OverflowError):
        raise AiUnavailableError("Cấu hình AI không hợp lệ", code="ai_invalid_configuration") from None
