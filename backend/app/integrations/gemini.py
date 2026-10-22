"""Gemini Interactions API, with local history, store=false and no automatic retries."""

import json
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import httpx
from google import genai
from google.genai import types
# google-genai 2.31.0 exposes Interactions errors through this compatibility hierarchy.
from google.genai._gaos.lib.compat_errors import (
    APIConnectionError, APIResponseValidationError, APIStatusError, APITimeoutError,
)
from pydantic import ValidationError

from app.core.ai_config import AiSettings
from app.services.exceptions import AiUnavailableError

from .ai import ChatCompletion, ToolCall


def _history(messages):
    instructions, steps = [], []
    call_names = {}
    for message in messages:
        role, content = message["role"], message.get("content")
        if role == "system":
            instructions.append(content or "")
        elif role == "assistant" and message.get("provider_steps"):
            steps.extend(message["provider_steps"])
            call_names.update({step["id"]: step["name"] for step in message["provider_steps"]
                               if step["type"] == "function_call"})
        elif role == "tool":
            name = call_names.get(message["tool_call_id"])
            if not name:
                raise AiUnavailableError("AI trả mã công cụ không hợp lệ.", code="ai_invalid_output")
            # A JSON string preserves the complete tool result through the SDK's object union.
            steps.append({"type": "function_result", "name": name,
                          "call_id": message["tool_call_id"], "result": content or "{}"})
        else:
            if content:
                steps.append({"type": "user_input" if role == "user" else "model_output",
                              "content": [{"type": "text", "text": content}]})
            for call in message.get("tool_calls", []):
                function = call["function"]
                call_names[call["id"]] = function["name"]
                steps.append({"type": "function_call", "id": call["id"], "name": function["name"],
                              "arguments": json.loads(function["arguments"])})
    return "\n\n".join(instructions), steps


def _error_details(body):
    entries = body if isinstance(body, list) else [body]
    for entry in entries:
        if isinstance(entry, dict):
            details = entry.get("error", entry)
            if isinstance(details, dict):
                return details
    return {}


def _retry_after(error):
    header = error.response.headers.get("retry-after")
    try:
        if header:
            try:
                seconds = float(header)
            except ValueError:
                seconds = (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds()
            if math.isfinite(seconds):
                return min(86400, max(1, math.ceil(seconds)))
    except (ValueError, TypeError, OverflowError):
        pass
    details = _error_details(error.body)
    for detail in details.get("details", []):
        if isinstance(detail, dict) and str(detail.get("@type", "")).endswith("google.rpc.RetryInfo"):
            try:
                seconds = float(str(detail["retryDelay"]).removesuffix("s"))
                if math.isfinite(seconds):
                    return min(86400, max(1, math.ceil(seconds)))
            except (KeyError, ValueError, TypeError, OverflowError):
                pass
    return 60


class GeminiChatModel:
    def __init__(self, settings: AiSettings):
        self.settings = settings

    def complete(self, messages, *, tools=None, timeout_seconds=None):
        settings = self.settings
        if not settings.api_key or settings.api_key == "dan_api_key_cua_ban_tai_day":
            raise AiUnavailableError("Trợ lý AI chưa được cấu hình", code="ai_not_configured")
        instruction, steps = _history(messages)
        config = {"max_output_tokens": settings.max_output_tokens,
                  "thinking_level": "low", "thinking_summaries": "none"}
        if tools:
            config["tool_choice"] = "any"
        try:
            with genai.Client(api_key=settings.api_key, http_options=types.HttpOptions(
                base_url="https://generativelanguage.googleapis.com", api_version="v1beta",
                timeout=math.ceil((timeout_seconds if timeout_seconds is not None else settings.timeout_seconds) * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            )) as client:
                interactions = client.interactions
                # SDK 2.31.0 normalizes attempts=0 to 1, then treats it as a retry count in Interactions.
                # Disable that resource's retry policy explicitly; HTTP contract tests enforce one request.
                interactions.sdk_configuration.retry_config = None
                response = interactions.create(
                    model=settings.model,
                    input=steps,
                    system_instruction=instruction,
                    tools=[{"type": "function", **tool["function"]} for tool in tools] if tools else [],
                    generation_config=config, store=False,
                )
        except (APITimeoutError, httpx.TimeoutException):
            raise AiUnavailableError("AI phản hồi quá thời gian chờ. Vui lòng thử lại.") from None
        except (APIConnectionError, httpx.TransportError):
            raise AiUnavailableError("Chưa kết nối được AI. Vui lòng thử lại.") from None
        except APIResponseValidationError:
            raise AiUnavailableError("AI trả kết quả không hợp lệ.", code="ai_invalid_output") from None
        except APIStatusError as error:
            if error.status_code == 429:
                raise AiUnavailableError("AI tạm hết hạn mức. Vui lòng thử lại sau.",
                    code="ai_quota_exceeded", retry_after_seconds=_retry_after(error)) from None
            if error.status_code in (400, 401, 403, 404):
                raise AiUnavailableError("Kết nối AI cần được kiểm tra cấu hình.",
                                         code="ai_provider_configuration_error") from None
            raise AiUnavailableError("AI tạm thời không khả dụng. Vui lòng thử lại.") from None
        except (ValidationError, ValueError, TypeError):
            raise AiUnavailableError("AI trả kết quả không hợp lệ.", code="ai_invalid_output") from None
        if response.status not in ("completed", "requires_action") or response.errors:
            raise AiUnavailableError("AI chưa trả được câu trả lời hoàn chỉnh.", code="ai_invalid_output")
        original = tuple(step.model_dump(mode="json", by_alias=True, exclude_none=True) for step in response.steps or [])
        if any(step["type"] not in {"thought", "model_output", "function_call"} for step in original):
            raise AiUnavailableError("AI trả kết quả không được hỗ trợ.", code="ai_invalid_output")
        calls = tuple(ToolCall(step["id"], step["name"], json.dumps(step["arguments"], ensure_ascii=False))
                      for step in original if step["type"] == "function_call")
        content = "\n".join(part["text"] for step in original if step["type"] == "model_output"
                            for part in step.get("content", []) if part.get("type") == "text").strip()
        if (len(content) > 5000 or (calls and (not tools or len(calls) > 2))
                or (not calls and (not content or response.status != "completed"))
                or any(step.get("error") for step in original)):
            raise AiUnavailableError("AI chưa trả được câu trả lời hoàn chỉnh.", code="ai_invalid_output")
        usage = response.usage
        inputs = (usage.total_input_tokens or 0) if usage else 0
        outputs = (usage.total_output_tokens or 0) if usage else 0
        if usage:
            # Include thinking tokens when the provider reports them outside visible output.
            outputs = max(outputs, (usage.total_tokens or 0) - inputs)
        return ChatCompletion(content, settings.model, inputs, outputs, calls, original)
