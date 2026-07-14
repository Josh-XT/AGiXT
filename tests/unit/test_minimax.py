import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "agixt" / "extensions" / "minimax.py"


def _load_minimax_module():
    extensions_stub = types.ModuleType("Extensions")
    extensions_stub.Extensions = type("Extensions", (), {})
    globals_stub = types.ModuleType("Globals")
    globals_stub.getenv = lambda _name, default="": default

    previous_extensions = sys.modules.get("Extensions")
    previous_globals = sys.modules.get("Globals")
    sys.modules["Extensions"] = extensions_stub
    sys.modules["Globals"] = globals_stub
    try:
        spec = importlib.util.spec_from_file_location("minimax_extension", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_extensions is None:
            sys.modules.pop("Extensions", None)
        else:
            sys.modules["Extensions"] = previous_extensions
        if previous_globals is None:
            sys.modules.pop("Globals", None)
        else:
            sys.modules["Globals"] = previous_globals


minimax_module = _load_minimax_module()


class FakeResponse:
    def __init__(self, data=None, lines=None):
        self.data = data or {}
        self.lines = lines or []

    def raise_for_status(self):
        return None

    def json(self):
        return self.data

    def iter_lines(self):
        return iter(self.lines)


@pytest.mark.parametrize(
    ("api_uri", "expected_url", "protocol"),
    [
        ("global_en", "https://api.minimax.io/v1/chat/completions", "openai"),
        ("cn_zh", "https://api.minimaxi.com/v1/chat/completions", "openai"),
        (
            "global_en_anthropic",
            "https://api.minimax.io/anthropic/v1/messages",
            "anthropic",
        ),
        (
            "cn_zh_anthropic",
            "https://api.minimaxi.com/anthropic/v1/messages",
            "anthropic",
        ),
    ],
)
def test_routes_requests_to_each_regional_protocol(api_uri, expected_url, protocol):
    response_data = (
        {
            "content": [
                {"type": "thinking", "thinking": "internal"},
                {"type": "text", "text": "ready"},
            ]
        }
        if protocol == "anthropic"
        else {"choices": [{"message": {"content": "ready"}}]}
    )
    provider = minimax_module.minimax(
        MINIMAX_API_KEY="test-key",
        MINIMAX_API_URI=api_uri,
        MINIMAX_MAX_OUTPUT_TOKENS=32,
    )

    with patch.object(
        minimax_module.requests, "post", return_value=FakeResponse(response_data)
    ) as request:
        result = asyncio.run(provider.inference("Hello"))

    assert result == "ready"
    assert request.call_args.args[0] == expected_url
    payload = request.call_args.kwargs["json"]
    headers = request.call_args.kwargs["headers"]
    assert payload["service_tier"] == "standard"
    assert "thinking" not in payload
    if protocol == "anthropic":
        assert headers["x-api-key"] == "test-key"
        assert headers["anthropic-version"] == "2023-06-01"
        assert "Authorization" not in headers
        assert payload["max_tokens"] == 32
        assert "max_completion_tokens" not in payload
        assert payload["messages"][0]["content"][0]["type"] == "text"
    else:
        assert headers["Authorization"] == "Bearer test-key"
        assert "x-api-key" not in headers
        assert payload["max_completion_tokens"] == 32
        assert "max_tokens" not in payload


def test_anthropic_requests_use_native_multimodal_blocks():
    provider = minimax_module.minimax(
        MINIMAX_API_KEY="test-key",
        MINIMAX_API_URI="global_en_anthropic",
        MINIMAX_MAX_OUTPUT_TOKENS=32,
    )

    with patch.object(
        minimax_module.requests,
        "post",
        return_value=FakeResponse({"content": [{"type": "text", "text": "ready"}]}),
    ) as request:
        asyncio.run(
            provider.inference(
                "Inspect these",
                images=[
                    "https://example.com/image.png",
                    "data:image/png;base64,AA==",
                    "mm_file://video-id",
                ],
            )
        )

    content = request.call_args.kwargs["json"]["messages"][0]["content"]
    assert content[1] == {
        "type": "image",
        "source": {"type": "url", "url": "https://example.com/image.png"},
    }
    assert content[2] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "AA=="},
    }
    assert content[3] == {
        "type": "video",
        "source": {"type": "url", "url": "mm_file://video-id"},
    }


def test_anthropic_stream_maps_text_reasoning_and_finish_chunks():
    response = FakeResponse(
        lines=[
            b'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"plan"}}',
            b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"answer"}}',
            b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
        ]
    )

    chunks = list(minimax_module.parse_anthropic_sse_stream(response))

    assert chunks[0].choices[0].delta.reasoning_content == "plan"
    assert chunks[1].choices[0].delta.content == "answer"
    assert chunks[2].choices[0].finish_reason == "end_turn"


def test_target_model_defaults_preserve_context_and_output_semantics():
    m3 = minimax_module.minimax(MINIMAX_API_KEY="test-key")
    m27 = minimax_module.minimax(
        MINIMAX_API_KEY="test-key",
        MINIMAX_MODEL="MiniMax-M2.7",
        MINIMAX_THINKING="disabled",
    )

    assert (m3.MAX_TOKENS, m3.MAX_OUTPUT_TOKENS, m3.AI_TOP_P) == (
        1_000_000,
        131_072,
        0.95,
    )
    assert (m27.MAX_TOKENS, m27.MAX_OUTPUT_TOKENS, m27.AI_TOP_P) == (
        204_800,
        65_536,
        0.9,
    )
    assert m3.THINKING is None
    assert m27.THINKING == "always_on"


def test_provider_services_can_be_discovered_from_the_class():
    assert minimax_module.minimax.services() == ["llm", "vision"]


def test_rejects_versioned_anthropic_base_urls():
    with pytest.raises(ValueError, match="must end in /anthropic"):
        minimax_module.minimax(
            MINIMAX_API_KEY="test-key",
            MINIMAX_API_URI="https://api.minimax.io/anthropic/v1",
        )
