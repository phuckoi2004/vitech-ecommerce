"""Gemini SDK contract through HTTP MockTransport; no credentials or external calls required."""

import json

import httpx
import pytest
from google import genai

from app.core.ai_config import AiSettings, get_ai_settings
from app.integrations.gemini import GeminiChatModel
from app.services.ai_tools import tool_definitions
from app.services.exceptions import AiUnavailableError
from tests.test_ai_grounded import ask, grounded_shop  # noqa: F401 - shared isolated SQLite fixture


def mock_client(monkeypatch, respond):
    original = genai.Client

    def create(**kwargs):
        options = kwargs["http_options"].model_copy(update={
            "httpx_client": httpx.Client(transport=httpx.MockTransport(respond)),
        })
        return original(**{**kwargs, "http_options": options})

    monkeypatch.setattr("app.integrations.gemini.genai.Client", create)


def interaction(*steps, status="completed", usage=None):
    return {"id": "mock", "status": status, "model": "gemini-3.5-flash-lite", "steps": list(steps),
            "usage": usage or {"total_input_tokens": 10, "total_output_tokens": 5, "total_tokens": 15}}


def text(value):
    return {"type": "model_output", "content": [{"type": "text", "text": value}]}


def function(name="search_products", id_="lookup", **args):
    return {"type": "function_call", "id": id_, "name": name, "arguments": args}


def test_sdk_uses_interactions_stateless_history_timeout_and_content_only(monkeypatch):
    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(200, json=interaction(text("Xin chào")))

    mock_client(monkeypatch, respond)
    result = GeminiChatModel(AiSettings(api_key="secret-test")).complete([
        {"role": "system", "content": "Tiếng Việt"}, {"role": "user", "content": "Xin chào"},
    ], timeout_seconds=3)
    request = captured[0]
    body = json.loads(request.content)
    assert request.url.host == "generativelanguage.googleapis.com" and request.url.path == "/v1beta/interactions"
    assert request.headers["x-goog-api-key"] == "secret-test"
    assert body["model"] == "gemini-3.5-flash-lite" and body["store"] is False
    assert "previous_interaction_id" not in body and body["system_instruction"] == "Tiếng Việt"
    assert body["input"] == [{"type": "user_input", "content": [{"type": "text", "text": "Xin chào"}]}]
    assert body["generation_config"]["max_output_tokens"] == 2048
    assert request.extensions["timeout"]["read"] == 3
    assert result.content == "Xin chào" and (result.prompt_tokens, result.completion_tokens) == (10, 5)
    assert "secret-test" not in repr(AiSettings(api_key="secret-test"))


def test_tool_round_replays_original_thought_signature_and_result_id(monkeypatch):
    requests = []
    signature = {"type": "thought", "signature": "c2lnbmF0dXJl"}

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["store"] is False and "previous_interaction_id" not in body
        assert body["generation_config"]["tool_choice"] == "any"
        assert body["tools"][0]["type"] == "function" and "function" not in body["tools"][0]
        if len(requests) == 1:
            return httpx.Response(200, json=interaction(signature, function(category="laptop"), status="requires_action"))
        assert body["input"][-3] == signature
        assert body["input"][-2] == function(category="laptop")
        assert body["input"][-1] == {"type": "function_result", "name": "search_products",
                                    "call_id": "lookup", "result": '{"Products":[]}'}
        return httpx.Response(200, json=interaction(function("present_answer", "final", intent="no_results"), status="requires_action"))

    mock_client(monkeypatch, respond)
    model = GeminiChatModel(AiSettings(api_key="test"))
    history = [{"role": "user", "content": "Laptop"}]
    first = model.complete(history, tools=tool_definitions())
    assert first.tool_calls[0].name == "search_products" and "signature" not in repr(first)
    history.extend([
        {"role": "assistant", "content": None, "provider_steps": first.provider_steps},
        {"role": "tool", "tool_call_id": "lookup", "content": '{"Products":[]}'},
    ])
    assert model.complete(history, tools=tool_definitions(final_only=True)).tool_calls[0].name == "present_answer"
    assert {tool["name"] for tool in requests[-1]["tools"]} == {"present_answer"}


@pytest.mark.parametrize("provider_steps", [True, False])
def test_parallel_tool_results_keep_the_name_of_each_call(monkeypatch, provider_steps):
    calls = [function("search_products", "search", category="laptop"),
             function("list_offers", "offers")]
    assistant = {"role": "assistant", "content": None}
    if provider_steps:
        assistant["provider_steps"] = tuple(calls)
    else:
        assistant["tool_calls"] = [{"id": call["id"], "type": "function", "function": {
            "name": call["name"], "arguments": json.dumps(call["arguments"])}} for call in calls]

    def respond(request):
        results = json.loads(request.content)["input"][-2:]
        assert [(item["call_id"], item["name"]) for item in results] == [
            ("offers", "list_offers"), ("search", "search_products")]
        return httpx.Response(200, json=interaction(text("Đã nhận kết quả")))

    mock_client(monkeypatch, respond)
    result = GeminiChatModel(AiSettings(api_key="test")).complete([
        {"role": "user", "content": "Laptop và ưu đãi"}, assistant,
        {"role": "tool", "tool_call_id": "offers", "content": "{}"},
        {"role": "tool", "tool_call_id": "search", "content": "{}"},
    ])
    assert result.content == "Đã nhận kết quả"


def test_unmatched_tool_result_is_rejected_before_sending(monkeypatch):
    monkeypatch.setattr("app.integrations.gemini.genai.Client", lambda **_: pytest.fail("Must not send invalid history"))
    with pytest.raises(AiUnavailableError) as error:
        GeminiChatModel(AiSettings(api_key="test")).complete([
            {"role": "tool", "tool_call_id": "unknown", "content": "{}"},
        ])
    assert error.value.code == "ai_invalid_output"


def test_real_orchestrator_replays_gemini_steps_and_saves_only_verified_answer(monkeypatch, grounded_shop):
    shop, calls = grounded_shop, []
    signature = {"type": "thought", "signature": "c2lnbmF0dXJl"}

    def respond(request):
        assert shop.counters["connections"] == 0
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            return httpx.Response(200, json=interaction(signature,
                function(category="Laptop", max_price=20000000), status="requires_action"))
        assert body["input"][-3] == signature
        assert body["input"][-1]["call_id"] == "lookup"
        assert body["input"][-1]["name"] == "search_products"
        assert json.loads(body["input"][-1]["result"])["Products"]
        return httpx.Response(200, json=interaction(function("present_answer", "answer", intent="recommend",
            products=[{"product_id": shop.products["asus-zen"]}]), status="requires_action"))

    mock_client(monkeypatch, respond)
    service, _ = shop.service([])
    service.model = GeminiChatModel(service.settings)
    result = ask(shop, service)
    assert result.Status == "Completed" and len(result.AiMessages) == 2 and len(calls) == 2
    assert result.AiMessages[1].Metadata["ProductName"] == "asus-zen"
    assert "provider_steps" not in result.model_dump_json() and "signature" not in result.model_dump_json()


@pytest.mark.parametrize("status,code", [(429, "ai_quota_exceeded"), (400, "ai_provider_configuration_error"),
    (401, "ai_provider_configuration_error"), (403, "ai_provider_configuration_error"),
    (404, "ai_provider_configuration_error"), (500, "ai_unavailable"), (503, "ai_unavailable")])
def test_provider_errors_are_sanitized_and_not_retried(monkeypatch, status, code):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={"retry-after": "17.2"}, json={"error": {
            "code": status, "status": "RESOURCE_EXHAUSTED", "message": "secret-provider-message"}})

    mock_client(monkeypatch, respond)
    with pytest.raises(AiUnavailableError) as error:
        GeminiChatModel(AiSettings(api_key="secret-test")).complete([{"role": "user", "content": "Hi"}])
    assert error.value.code == code and "secret" not in str(error.value) and len(calls) == 1
    if status == 429:
        assert error.value.retry_after_seconds == 18


@pytest.mark.parametrize("delay,expected", [("2.2s", 3), ("bad", 60), ("999999s", 86400)])
def test_google_retry_info_is_used_without_retry_after_header(monkeypatch, delay, expected):
    mock_client(monkeypatch, lambda _: httpx.Response(429, json={"error": {"code": 429, "message": "quota",
        "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]}}))
    with pytest.raises(AiUnavailableError) as error:
        GeminiChatModel(AiSettings(api_key="test")).complete([])
    assert error.value.retry_after_seconds == expected


def test_google_array_error_preserves_retry_info_without_exposing_message(monkeypatch):
    mock_client(monkeypatch, lambda _: httpx.Response(429, json=[{"error": {"code": 429,
        "message": "secret-provider-body", "status": "RESOURCE_EXHAUSTED",
        "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "8.1s"}]}}]))
    with pytest.raises(AiUnavailableError) as error:
        GeminiChatModel(AiSettings(api_key="test")).complete([])
    assert error.value.retry_after_seconds == 9 and "secret" not in str(error.value)


def test_missing_key_never_creates_client(monkeypatch):
    monkeypatch.setattr("app.integrations.gemini.genai.Client", lambda **_: pytest.fail("Client must not be created"))
    with pytest.raises(AiUnavailableError) as error:
        GeminiChatModel(AiSettings()).complete([])
    assert error.value.code == "ai_not_configured"


@pytest.mark.parametrize("payload", [interaction(status="incomplete"), interaction(status="failed"),
    interaction(), interaction(text("x" * 5001)), interaction(function(), function(id_="two"), function(id_="three")),
    interaction({"type": "thought", "signature": "c2lnbmF0dXJl"})])
def test_incomplete_or_invalid_output_is_rejected(monkeypatch, payload):
    mock_client(monkeypatch, lambda _: httpx.Response(200, json=payload))
    with pytest.raises(AiUnavailableError):
        GeminiChatModel(AiSettings(api_key="test")).complete([], tools=tool_definitions())


@pytest.mark.parametrize("exception", [httpx.ReadTimeout, httpx.ConnectError])
def test_network_errors_are_mapped_without_retry(monkeypatch, exception):
    calls = []

    def respond(request):
        calls.append(request)
        raise exception("secret-test", request=request)

    mock_client(monkeypatch, respond)
    with pytest.raises(AiUnavailableError) as error:
        GeminiChatModel(AiSettings(api_key="test")).complete([])
    assert len(calls) == 1 and "secret-test" not in str(error.value)


def test_usage_counts_thinking_and_does_not_expose_thoughts(monkeypatch):
    mock_client(monkeypatch, lambda _: httpx.Response(200, json=interaction(
        {"type": "thought", "signature": "c2lnbmF0dXJl", "summary": [{"type": "text", "text": "private-thought"}]},
        text("Xin chào"), usage={"total_input_tokens": 10, "total_output_tokens": 5, "total_thought_tokens": 3,
                                  "total_tokens": 18})))
    result = GeminiChatModel(AiSettings(api_key="test")).complete([])
    assert result.completion_tokens == 8 and "private-thought" not in repr(result)


def test_config_reads_gemini_and_rejects_invalid_values_without_secrets(monkeypatch):
    monkeypatch.setattr("app.core.ai_config.load_environment", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    get_ai_settings.cache_clear()
    try:
        assert get_ai_settings().api_key == "secret-test" and get_ai_settings().model == "gemini-3.8-flash"
        get_ai_settings.cache_clear()
        monkeypatch.setenv("AI_TIMEOUT_SECONDS", "not-a-number-secret")
        with pytest.raises(AiUnavailableError) as error:
            get_ai_settings()
        assert "secret" not in str(error.value)
    finally:
        get_ai_settings.cache_clear()
