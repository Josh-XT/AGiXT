import asyncio
import base64
import importlib.util
import io
import sys
import types
import wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "agixt" / "extensions" / "minimax_speech.py"


@pytest.fixture
def speech_module(monkeypatch):
    """Isolate application startup dependencies from speech API unit tests."""
    extensions = types.ModuleType("Extensions")
    extensions.Extensions = object
    settings = types.ModuleType("Globals")
    settings.getenv = lambda name, default="": {
        "AGIXT_URI": "https://agixt.example",
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "%(message)s",
    }.get(name, default)
    monkeypatch.setitem(sys.modules, "Extensions", extensions)
    monkeypatch.setitem(sys.modules, "Globals", settings)
    spec = importlib.util.spec_from_file_location("minimax_speech", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def audio():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(32000)
        output.writeframes(b"\x00\x00" * 32)
    return buffer.getvalue()


def mock_response(monkeypatch, speech_module, payload):
    response = MagicMock()
    response.__enter__.return_value = response
    response.json.return_value = payload
    post = MagicMock(return_value=response)
    monkeypatch.setattr(speech_module.requests, "post", post)
    return post, response


def success(audio):
    return {
        "base_resp": {"status_code": 0},
        "data": {"status": 2, "audio": audio.hex()},
    }


@pytest.mark.parametrize(
    ("region", "endpoint"),
    [
        ("global_en", "https://api.minimax.io/v1/t2a_v2"),
        ("cn_zh", "https://api.minimaxi.com/v1/t2a_v2"),
    ],
)
def test_synthesis_returns_base64_wav_for_agent_pipeline(
    speech_module, monkeypatch, audio, region, endpoint
):
    post, response = mock_response(monkeypatch, speech_module, success(audio))
    provider = speech_module.minimax_speech(
        MINIMAX_API_KEY="test-key", MINIMAX_TTS_REGION=region
    )

    result = asyncio.run(provider.text_to_speech("Hello!"))

    assert isinstance(result, str)
    assert base64.b64decode(result) == audio
    post.assert_called_once_with(
        endpoint,
        headers={
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
        },
        json={
            "model": "speech-2.8-hd",
            "text": "Hello!",
            "stream": False,
            "output_format": "hex",
            "voice_setting": {"voice_id": "English_expressive_narrator"},
            "audio_setting": {"format": "wav"},
        },
        timeout=120,
    )
    response.raise_for_status.assert_called_once()
    response.__exit__.assert_called_once()


def test_environment_settings_and_explicit_overrides(speech_module, monkeypatch):
    environment = {
        "MINIMAX_API_KEY": "environment-key",
        "MINIMAX_TTS_MODEL": "configured-environment-model",
        "MINIMAX_TTS_REGION": "cn_zh",
        "MINIMAX_TTS_VOICE": "account-voice",
    }
    monkeypatch.setattr(
        speech_module, "getenv", lambda name, default="": environment.get(name, default)
    )
    provider = speech_module.minimax_speech()
    assert provider.is_configured()
    assert provider.MINIMAX_API_KEY == "environment-key"
    assert provider.MODEL == "configured-environment-model"
    assert provider.VOICE == "account-voice"
    assert provider.API_URI == "https://api.minimaxi.com/v1/t2a_v2"
    explicit = speech_module.minimax_speech(
        MINIMAX_API_KEY="agent-key",
        MINIMAX_TTS_MODEL="configured-agent-model",
        MINIMAX_TTS_VOICE="agent-voice",
    )
    assert explicit.MINIMAX_API_KEY == "agent-key"
    assert explicit.MODEL == "configured-agent-model"
    assert explicit.VOICE == "agent-voice"


def test_discovery_reports_tts_service_and_settings(speech_module):
    spec = importlib.util.spec_from_file_location(
        "speech_provider_registry", PROJECT_ROOT / "agixt" / "Providers.py"
    )
    registry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(registry)
    registry._ai_provider_cache = {
        "minimax_speech": {
            "class": speech_module.minimax_speech,
            "module": speech_module,
            "file": str(MODULE_PATH),
        }
    }
    registry._ai_provider_cache_time = registry.time.time()

    assert registry.get_providers_by_service("tts") == ["minimax_speech"]
    assert registry.get_providers_by_service("llm") == []
    details = registry.get_providers_with_details()["minimax_speech"]
    assert details["services"] == ["tts"]
    assert details["settings"]["MINIMAX_TTS_MODEL"] == "speech-2.8-hd"
    assert "MINIMAX_API_KEY" in details["settings"]


@pytest.mark.parametrize(
    "key", ["", " ", "none", "null", "false", "0", "your_minimax_api_key"]
)
def test_missing_key_never_sends_request(speech_module, monkeypatch, key):
    post, _ = mock_response(monkeypatch, speech_module, {})
    provider = speech_module.minimax_speech(MINIMAX_API_KEY=key)
    assert not provider.is_configured()
    with pytest.raises(ValueError, match="not configured"):
        asyncio.run(provider.text_to_speech("Hello"))
    post.assert_not_called()


@pytest.mark.parametrize("text", ["", " ", "x" * 10000, None])
def test_invalid_text_never_sends_request(speech_module, monkeypatch, text):
    post, _ = mock_response(monkeypatch, speech_module, {})
    provider = speech_module.minimax_speech(MINIMAX_API_KEY="test-key")
    with pytest.raises(ValueError, match="1 to 9999"):
        asyncio.run(provider.text_to_speech(text))
    post.assert_not_called()


def test_unknown_region_is_rejected(speech_module):
    with pytest.raises(ValueError, match="global_en or cn_zh"):
        speech_module.minimax_speech(MINIMAX_TTS_REGION="unknown")


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"base_resp": {"status_code": 1004}, "data": None},
        {"base_resp": {"status_code": 0}, "data": None},
        {"base_resp": {"status_code": 0}, "data": {"status": 1, "audio": "00"}},
        success(b""),
        {"base_resp": {"status_code": 0}, "data": {"status": 2, "audio": "not-hex"}},
        {"base_resp": {"status_code": 0}, "data": {"status": 2, "audio": " "}},
    ],
)
def test_errors_never_create_audio_file(speech_module, monkeypatch, tmp_path, payload):
    mock_response(monkeypatch, speech_module, payload)
    provider = speech_module.minimax_speech(
        MINIMAX_API_KEY="test-key", conversation_directory=str(tmp_path)
    )
    with pytest.raises(ValueError):
        asyncio.run(provider.text_to_speech_command("Hello"))
    assert list(tmp_path.iterdir()) == []


def test_http_error_propagates(speech_module, monkeypatch):
    post, response = mock_response(monkeypatch, speech_module, {})
    response.raise_for_status.side_effect = requests.HTTPError("HTTP 429")
    provider = speech_module.minimax_speech(MINIMAX_API_KEY="test-key")
    with pytest.raises(requests.HTTPError):
        asyncio.run(provider.text_to_speech("Hello"))
    post.assert_called_once()
    response.json.assert_not_called()


def test_command_writes_wav_in_conversation_workspace(
    speech_module, monkeypatch, tmp_path, audio
):
    mock_response(monkeypatch, speech_module, success(audio))
    workspace = tmp_path / "conversation"
    provider = speech_module.minimax_speech(
        MINIMAX_API_KEY="test-key",
        conversation_directory=str(workspace),
        output_url="https://agixt.example/outputs/agent/conversation/",
    )

    result = asyncio.run(provider.commands["Text to Speech with MiniMax"]("Hello"))

    files = list(workspace.glob("*.wav"))
    assert len(files) == 1
    assert files[0].read_bytes() == audio
    assert result == f"https://agixt.example/outputs/agent/conversation/{files[0].name}"
