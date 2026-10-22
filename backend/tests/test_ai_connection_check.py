"""Connection-check CLI keeps overrides local and never prints provider error messages or keys."""

from app.cli import check_gemini
from app.core.ai_config import AiSettings
from app.integrations.ai import ChatCompletion
from app.services.exceptions import AiUnavailableError


def test_cli_uses_explicit_model_and_timeout_without_changing_environment(monkeypatch, capsys):
    base = AiSettings(api_key="private-test-key")
    captured = []
    monkeypatch.setattr(check_gemini, "get_ai_settings", lambda: base)

    class Model:
        def __init__(self, settings):
            captured.append(settings)

        def complete(self, messages):
            return ChatCompletion("Xin chào VieTech", captured[-1].model, 10, 5)

    monkeypatch.setattr(check_gemini, "GeminiChatModel", Model)
    assert check_gemini.main(["--model", "gemini-3.8-flash", "--timeout", "5"]) == 0
    assert (captured[0].model, captured[0].timeout_seconds) == ("gemini-3.8-flash", 5)
    assert (base.model, base.timeout_seconds) == ("gemini-3.5-flash-lite", 120)
    output = capsys.readouterr().out
    assert "Xin chào" in output and "private-test-key" not in output


def test_cli_reports_http_status_without_provider_message(monkeypatch, capsys):
    monkeypatch.setattr(check_gemini, "get_ai_settings", lambda: AiSettings(api_key="private-test-key"))

    class ProviderFailure(Exception):
        status_code = 503

    class Model:
        def __init__(self, settings):
            pass

        def complete(self, messages):
            try:
                raise ProviderFailure("private-test-key: secret-provider-message")
            except ProviderFailure:
                raise AiUnavailableError("AI tạm thời không khả dụng.") from None

    monkeypatch.setattr(check_gemini, "GeminiChatModel", Model)
    assert check_gemini.main([]) == 1
    output = capsys.readouterr().out
    assert "HTTP 503" in output and "private-test-key" not in output and "secret-provider-message" not in output


def test_cli_missing_key_and_invalid_timeout_never_create_a_client(monkeypatch, capsys):
    monkeypatch.setattr(check_gemini, "get_ai_settings", lambda: AiSettings())
    assert check_gemini.main([]) == 1
    assert "ai_not_configured" in capsys.readouterr().out
    assert check_gemini.main(["--timeout", "0"]) == 1
    assert "ai_invalid_configuration" in capsys.readouterr().out
