"""Standalone Gemini connection check; never imports the database or application routers."""

import argparse
from dataclasses import replace

from app.core.ai_config import get_ai_settings
from app.integrations.gemini import GeminiChatModel
from app.services.exceptions import AiUnavailableError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kiểm tra Gemini, không truy cập database hoặc in API key.")
    parser.add_argument("--model", help="Model cần thử; không thay đổi cấu hình website.")
    parser.add_argument("--timeout", type=float, help="Thời gian chờ chẩn đoán (giây); không đổi deadline website.")
    args = parser.parse_args(argv)
    try:
        settings = get_ai_settings()
        overrides = {}
        if args.model is not None:
            overrides["model"] = args.model
        if args.timeout is not None:
            overrides["timeout_seconds"] = args.timeout
        settings = replace(settings, **overrides)
        result = GeminiChatModel(settings).complete([
            {"role": "system", "content": "Trả lời bằng tiếng Việt, chỉ một câu ngắn."},
            {"role": "user", "content": "Hãy chào khách hàng của cửa hàng VieTech."},
        ])
    except AiUnavailableError as error:
        print(f"{error.code}: {error.message}")
        source = error.__context__
        status = getattr(source, "status_code", None)
        if isinstance(status, int) and 400 <= status <= 599:
            print(f"Google trả HTTP {status}. Không tự retry hoặc đổi model.")
        elif type(source).__name__ in {"APITimeoutError", "ReadTimeout", "ConnectTimeout"}:
            print("Kết nối Gemini hết thời gian chờ; chưa xác nhận được câu trả lời từ model.")
        if error.code == "ai_not_configured":
            print("Điền GEMINI_API_KEY trong backend/.env rồi chạy lại.")
        if error.retry_after_seconds:
            print(f"Thử lại sau {error.retry_after_seconds} giây.")
        return 1
    print(result.content)
    print(f"Model: {result.model}; token: {result.prompt_tokens}+{result.completion_tokens}; store=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
