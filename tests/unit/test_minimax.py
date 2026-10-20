import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "agixt" / "extensions" / "minimax.py"


def _load_minimax_module(settings=None):
    extensions_stub = types.ModuleType("Extensions")
    extensions_stub.Extensions = type("Extensions", (), {})
    globals_stub = types.ModuleType("Globals")
    globals_stub.getenv = lambda name, default="": (settings or {}).get(name, default)

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
    assert payload["model"] == "MiniMax-M3.1-Flash"
    assert "service_tier" not in payload
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


@pytest.mark.parametrize("protocol", ["openai", "anthropic"])
def test_local_mov_files_use_the_documented_base64_media_type(tmp_path, protocol):
    media_file = tmp_path / "clip.mov"
    media_file.write_bytes(b"video")

    content = minimax_module._media_content_part(str(media_file), protocol)

    if protocol == "anthropic":
        assert content == {
            "type": "video",
            "source": {
                "type": "base64",
                "media_type": "video/mov",
                "data": "dmlkZW8=",
            },
        }
    else:
        assert content == {
            "type": "video_url",
            "video_url": {"url": "data:video/mov;base64,dmlkZW8="},
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
    flash = minimax_module.minimax(MINIMAX_API_KEY="test-key")
    m3 = minimax_module.minimax(MINIMAX_API_KEY="test-key", MINIMAX_MODEL="MiniMax-M3")
    assert flash.AI_MODEL == "MiniMax-M3.1-Flash"
    assert (flash.MAX_TOKENS, flash.MAX_OUTPUT_TOKENS, flash.AI_TOP_P) == (
        1_000_000,
        131_072,
        0.95,
    )
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


@pytest.mark.parametrize(
    ("model", "max_output_tokens"),
    [
        ("MiniMax-M3.1-Flash", 524_289),
        ("MiniMax-M3", 524_289),
        ("MiniMax-M2.7", 204_801),
    ],
)
def test_rejects_output_tokens_above_model_limits(model, max_output_tokens):
    with pytest.raises(ValueError, match=f"{model} output limit"):
        minimax_module.minimax(
            MINIMAX_API_KEY="test-key",
            MINIMAX_MODEL=model,
            MINIMAX_MAX_OUTPUT_TOKENS=max_output_tokens,
        )


def test_provider_services_can_be_discovered_from_the_class():
    assert minimax_module.minimax.services() == ["llm", "vision"]


@pytest.fixture
def http_requests(monkeypatch):
    """Capture the serialized request after Requests prepares the HTTP body."""
    captured = []

    def send(_adapter, request, **kwargs):
        captured.append(request)
        response = minimax_module.requests.Response()
        response.status_code = 200
        response.request = request
        if request.url.endswith("/messages"):
            data = {"content": [{"type": "text", "text": "ready"}]}
        else:
            data = {"choices": [{"message": {"content": "ready"}}]}
        response._content = json.dumps(data).encode()
        response.headers["Content-Type"] = "application/json"
        if json.loads(request.body).get("stream"):
            if request.url.endswith("/messages"):
                events = [
                    {
                        "type": "content_block_delta",
                        "delta": {"type": "thinking_delta", "thinking": "plan"},
                    },
                    {
                        "type": "content_block_delta",
                        "delta": {"type": "text_delta", "text": "ready"},
                    },
                ]
            else:
                events = [
                    {"choices": [{"delta": {"reasoning_content": "plan"}}]},
                    {"choices": [{"delta": {"content": "ready"}}]},
                ]
            response._content = "".join(
                f"data: {json.dumps(event)}\n\n" for event in events
            ).encode()
            response._content_consumed = True
            response.headers["Content-Type"] = "text/event-stream"
        return response

    monkeypatch.setattr(minimax_module.requests.adapters.HTTPAdapter, "send", send)
    return captured


@pytest.mark.parametrize("api_uri", list(minimax_module.API_URIS))
@pytest.mark.parametrize("effort", ["", "low", "medium", "high", "xhigh", "max"])
def test_flash_serialized_request(api_uri, effort, http_requests):
    provider = minimax_module.minimax(
        MINIMAX_API_KEY="test-key",
        MINIMAX_API_URI=api_uri,
        MINIMAX_REASONING_EFFORT=effort,
        MINIMAX_THINKING="adaptive",
        MINIMAX_MAX_OUTPUT_TOKENS=524_288,
    )
    assert asyncio.run(provider.generate_response_command("Hello")) == "ready"
    request = http_requests[0]
    payload = json.loads(request.body)
    assert payload["model"] == "MiniMax-M3.1-Flash"
    assert payload["thinking"] == {"type": "adaptive"}
    assert "service_tier" not in payload
    assert "reasoning_split" not in payload
    assert request.method == "POST"
    anthropic = api_uri.endswith("anthropic")
    assert request.url == minimax_module.API_URIS[api_uri] + (
        "/v1/messages" if anthropic else "/chat/completions"
    )
    if anthropic:
        assert payload["max_tokens"] == 524_288
        assert "reasoning_effort" not in payload
        assert payload.get("output_config") == ({"effort": effort} if effort else None)
        assert request.headers["x-api-key"] == "test-key"
    else:
        assert payload["max_completion_tokens"] == 524_288
        assert "output_config" not in payload
        assert payload.get("reasoning_effort") == (effort or None)
        assert request.headers["Authorization"] == "Bearer test-key"


@pytest.mark.parametrize("api_uri", list(minimax_module.API_URIS))
@pytest.mark.parametrize("thinking", ["", "adaptive", "disabled"])
def test_saved_m3_preserves_thinking_and_tier(api_uri, thinking, http_requests):
    with patch.object(minimax_module, "getenv", return_value="MiniMax-M3.1-Flash"):
        provider = minimax_module.minimax(
            MINIMAX_API_KEY="test-key",
            MINIMAX_API_URI=api_uri,
            MINIMAX_MODEL="MiniMax-M3",
            MINIMAX_THINKING=thinking,
            MINIMAX_SERVICE_TIER="priority",
            MINIMAX_REASONING_EFFORT="high",
        )
    asyncio.run(provider.inference("Hello"))
    payload = json.loads(http_requests[0].body)
    assert payload["model"] == "MiniMax-M3"
    assert payload["service_tier"] == "priority"
    assert payload.get("thinking") == ({"type": thinking} if thinking else None)
    assert "reasoning_effort" not in payload
    assert "output_config" not in payload


@pytest.mark.parametrize(
    "model", ["MiniMax-M2.7", "custom-model", "MiniMax-M3.1-Flash"]
)
@pytest.mark.parametrize(
    "base", ["https://custom.example/v1", "https://custom.example/anthropic"]
)
def test_explicit_models_and_custom_endpoints_are_preserved(model, base, http_requests):
    with patch.object(minimax_module, "getenv", return_value="another-model"):
        provider = minimax_module.minimax(
            MINIMAX_API_KEY="test-key", MINIMAX_MODEL=model, MINIMAX_API_URI=base
        )
    asyncio.run(provider.inference("Hello"))
    payload = json.loads(http_requests[0].body)
    assert payload["model"] == model
    assert http_requests[0].url.startswith(base + "/")
    assert "thinking" not in payload
    assert "service_tier" not in payload


@pytest.mark.parametrize("api_uri", list(minimax_module.API_URIS))
@pytest.mark.parametrize("model", ["MiniMax-M3.1-Flash", "MiniMax-M3"])
def test_serialized_multimodal_payload_is_preserved(api_uri, model, http_requests):
    provider = minimax_module.minimax(
        MINIMAX_API_KEY="test-key", MINIMAX_API_URI=api_uri, MINIMAX_MODEL=model
    )
    asyncio.run(
        provider.inference(
            "Inspect", images=["data:image/png;base64,AA==", "mm_file://video-id"]
        )
    )
    content = json.loads(http_requests[0].body)["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "Inspect"}
    if api_uri.endswith("anthropic"):
        assert content[1] == {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "AA=="},
        }
        assert content[2] == {
            "type": "video",
            "source": {"type": "url", "url": "mm_file://video-id"},
        }
    else:
        assert content[1] == {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AA=="},
        }
        assert content[2] == {
            "type": "video_url",
            "video_url": {"url": "mm_file://video-id"},
        }


@pytest.mark.parametrize(
    "settings",
    [
        {"MINIMAX_THINKING": "disabled"},
        {"MINIMAX_REASONING_EFFORT": "none"},
        {"MINIMAX_REASONING_EFFORT": "invalid"},
        {"MINIMAX_SERVICE_TIER": "priority"},
    ],
)
def test_invalid_flash_options_fail_before_http(settings, http_requests):
    with pytest.raises(ValueError):
        minimax_module.minimax(MINIMAX_API_KEY="test-key", **settings)
    assert not http_requests


def test_provider_discovery_default_reaches_http(http_requests):
    globals_stub = types.ModuleType("Globals")
    globals_stub.getenv = lambda name: {
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "%(message)s",
        "DISABLED_PROVIDERS": "",
    }[name]
    with patch.dict(sys.modules, {"Globals": globals_stub}):
        spec = importlib.util.spec_from_file_location(
            "provider_discovery", PROJECT_ROOT / "agixt" / "Providers.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    with patch.object(
        module,
        "_get_ai_provider_extensions",
        return_value={"minimax": {"class": minimax_module.minimax}},
    ):
        options = module.get_provider_options("minimax")
    assert options["MINIMAX_MODEL"] == "MiniMax-M3.1-Flash"
    options["MINIMAX_API_KEY"] = "test-key"
    provider = minimax_module.minimax(**options)
    asyncio.run(provider.inference("Hello"))
    payload = json.loads(http_requests[0].body)
    assert payload["model"] == "MiniMax-M3.1-Flash"
    assert "thinking" not in payload
    assert "reasoning_effort" not in payload
    assert "output_config" not in payload
    assert "service_tier" not in payload


@pytest.mark.parametrize("api_uri", list(minimax_module.API_URIS))
def test_flash_stream_preserves_reasoning_and_text(api_uri, http_requests):
    provider = minimax_module.minimax(
        MINIMAX_API_KEY="test-key", MINIMAX_API_URI=api_uri
    )
    chunks = list(asyncio.run(provider.inference("Hello", stream=True)))
    assert chunks[0].choices[0].delta.reasoning_content == "plan"
    assert chunks[1].choices[0].delta.content == "ready"
    assert json.loads(http_requests[0].body)["stream"] is True


@pytest.mark.parametrize("model", ["MiniMax-M3", "MiniMax-M2.7", "custom-model"])
def test_environment_default_and_explicit_selection_are_preserved(model, http_requests):
    module = _load_minimax_module({"MINIMAX_MODEL": model})
    provider = module.minimax(MINIMAX_API_KEY="test-key")
    asyncio.run(provider.inference("Hello"))
    assert json.loads(http_requests[-1].body)["model"] == model
    provider = module.minimax(
        MINIMAX_API_KEY="test-key", MINIMAX_MODEL="MiniMax-M3.1-Flash"
    )
    asyncio.run(provider.inference("Hello"))
    assert json.loads(http_requests[-1].body)["model"] == "MiniMax-M3.1-Flash"


def test_rejects_versioned_anthropic_base_urls():
    with pytest.raises(ValueError, match="must end in /anthropic"):
        minimax_module.minimax(
            MINIMAX_API_KEY="test-key",
            MINIMAX_API_URI="https://api.minimax.io/anthropic/v1",
        )
