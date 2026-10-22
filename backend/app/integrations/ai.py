"""Provider-independent contract for the AI orchestrator and scripted test models."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatCompletion:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: tuple[ToolCall, ...] = ()
    # Kept only during inference, never in customer responses, logs or persisted chat history.
    # Stateless Gemini rounds must replay the original steps, including thought signatures.
    provider_steps: tuple[dict[str, Any], ...] = field(default=(), repr=False, compare=False)


class ChatModel(Protocol):
    def complete(self, messages: list[dict[str, Any]], *, tools: list[dict] | None = None,
                 timeout_seconds: float | None = None) -> ChatCompletion: ...
