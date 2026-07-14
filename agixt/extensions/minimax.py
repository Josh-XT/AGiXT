"""
MiniMax AI provider extension for AGiXT.

This extension supports MiniMax text, image, and video inference through the
OpenAI-compatible Chat Completions API and the Anthropic-compatible Messages
API. Set MINIMAX_API_URI to global_en or cn_zh for Chat Completions, or to
global_en_anthropic or cn_zh_anthropic for Messages. Custom Anthropic base URLs
must end in /anthropic; the adapter appends /v1/messages.
"""

import base64
import json
import logging
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

from Extensions import Extensions
from Globals import getenv

API_URIS = {
    "global_en": "https://api.minimax.io/v1",
    "cn_zh": "https://api.minimaxi.com/v1",
    "global_en_anthropic": "https://api.minimax.io/anthropic",
    "cn_zh_anthropic": "https://api.minimaxi.com/anthropic",
}
ANTHROPIC_API_VERSION = "2023-06-01"
MODEL_CONTEXT_WINDOWS = {
    "MiniMax-M3": 1_000_000,
    "MiniMax-M2.7": 204_800,
}
MODEL_OUTPUT_TOKEN_DEFAULTS = {
    "MiniMax-M3": 131_072,
    "MiniMax-M2.7": 65_536,
}
MODEL_TOP_P_DEFAULTS = {
    "MiniMax-M3": 0.95,
    "MiniMax-M2.7": 0.9,
}
MEDIA_TYPES = {
    ".jpg": ("image_url", "image/jpeg"),
    ".jpeg": ("image_url", "image/jpeg"),
    ".png": ("image_url", "image/png"),
    ".gif": ("image_url", "image/gif"),
    ".webp": ("image_url", "image/webp"),
    ".mp4": ("video_url", "video/mp4"),
    ".avi": ("video_url", "video/x-msvideo"),
    ".mov": ("video_url", "video/quicktime"),
    ".mkv": ("video_url", "video/x-matroska"),
}


class StreamChunk:
    """Provide the streaming interface expected by AGiXT."""

    def __init__(self, data: dict):
        self._data = data
        self.choices = [StreamChoice(choice) for choice in data.get("choices", [])]


class StreamChoice:
    """Wrap one streamed response choice."""

    def __init__(self, choice_data: dict):
        self.delta = StreamDelta(choice_data.get("delta", {}))
        self.finish_reason = choice_data.get("finish_reason")


class StreamDelta:
    """Expose streamed text and reasoning fields."""

    def __init__(self, delta_data: dict):
        self.content = delta_data.get("content")
        self.reasoning_content = delta_data.get("reasoning_content")
        self.reasoning_details = delta_data.get("reasoning_details")
        self.role = delta_data.get("role")


def _sse_payloads(response):
    """Yield JSON payloads from a server-sent event response."""
    for line in response.iter_lines():
        if not line:
            continue
        line_text = line.decode("utf-8") if isinstance(line, bytes) else line
        if not line_text.startswith("data:"):
            continue
        data_text = line_text[5:].lstrip()
        if data_text == "[DONE]":
            break
        try:
            yield json.loads(data_text)
        except json.JSONDecodeError:
            continue


def parse_sse_stream(response):
    """Parse an OpenAI-compatible stream into AGiXT stream chunks."""
    for data in _sse_payloads(response):
        yield StreamChunk(data)


def parse_anthropic_sse_stream(response):
    """Parse an Anthropic-compatible stream into AGiXT stream chunks."""
    for data in _sse_payloads(response):
        event_type = data.get("type")
        if event_type == "content_block_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta":
                chunk_delta = {"content": delta.get("text")}
            elif delta.get("type") == "thinking_delta":
                chunk_delta = {"reasoning_content": delta.get("thinking")}
            else:
                continue
            yield StreamChunk(
                {"choices": [{"delta": chunk_delta, "finish_reason": None}]}
            )
        elif event_type == "message_delta":
            finish_reason = data.get("delta", {}).get("stop_reason")
            if finish_reason:
                yield StreamChunk(
                    {"choices": [{"delta": {}, "finish_reason": finish_reason}]}
                )


def _media_type(media: str):
    if media.startswith("data:image/"):
        return "image_url", None
    if media.startswith("data:video/") or media.startswith("mm_file://"):
        return "video_url", None

    path = urlsplit(media).path if media.startswith(("http://", "https://")) else media
    media_type = MEDIA_TYPES.get(Path(path).suffix.lower())
    if media_type:
        return media_type
    if media.startswith(("http://", "https://")):
        return "image_url", None
    raise ValueError(f"Unsupported MiniMax media type: {media}")


def _media_content_part(media: str, protocol: str):
    content_type, mime_type = _media_type(media)
    if media.startswith(("http://", "https://", "data:", "mm_file://")):
        media_url = media
    else:
        with open(media, "rb") as media_file:
            encoded_media = base64.b64encode(media_file.read()).decode("utf-8")
        media_url = f"data:{mime_type};base64,{encoded_media}"

    if protocol == "anthropic":
        block_type = "image" if content_type == "image_url" else "video"
        if media_url.startswith("data:"):
            header, encoded_media = media_url.split(",", 1)
            if not header.endswith(";base64"):
                raise ValueError("MiniMax data URLs must use base64 encoding")
            source = {
                "type": "base64",
                "media_type": header.removeprefix("data:").removesuffix(";base64"),
                "data": encoded_media,
            }
        else:
            source = {"type": "url", "url": media_url}
        return {"type": block_type, "source": source}

    return {"type": content_type, content_type: {"url": media_url}}


class minimax(Extensions):
    """MiniMax provider with regional Chat Completions and Messages endpoints.

    Use global_en or cn_zh for the OpenAI-compatible protocol. Use
    global_en_anthropic or cn_zh_anthropic for the Anthropic-compatible
    protocol. A blank thinking setting keeps each protocol's native default.
    """

    CATEGORY = "AI Provider"
    friendly_name = "MiniMax"
    SERVICES = ["llm", "vision"]

    def __init__(
        self,
        MINIMAX_API_KEY: str = "",
        MINIMAX_MODEL: str = "MiniMax-M3",
        MINIMAX_API_URI: str = API_URIS["global_en"],
        MINIMAX_MAX_TOKENS: int = 0,
        MINIMAX_MAX_OUTPUT_TOKENS: int = 0,
        MINIMAX_TEMPERATURE: float = 1.0,
        MINIMAX_TOP_P: float = None,
        MINIMAX_THINKING: str = "",
        MINIMAX_SERVICE_TIER: str = "standard",
        MINIMAX_WAIT_BETWEEN_REQUESTS: int = 0,
        MINIMAX_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        if not MINIMAX_API_KEY:
            MINIMAX_API_KEY = getenv("MINIMAX_API_KEY", "")
        if not MINIMAX_MODEL or MINIMAX_MODEL == "MiniMax-M3":
            MINIMAX_MODEL = getenv("MINIMAX_MODEL", "MiniMax-M3")
        if not MINIMAX_API_URI or MINIMAX_API_URI == API_URIS["global_en"]:
            MINIMAX_API_URI = getenv(
                "MINIMAX_API_URI",
                getenv("MINIMAX_BASE_URI", API_URIS["global_en"]),
            )

        self.MINIMAX_API_KEY = MINIMAX_API_KEY
        self.AI_MODEL = MINIMAX_MODEL or "MiniMax-M3"
        self.API_URI = (
            API_URIS.get(MINIMAX_API_URI, MINIMAX_API_URI or API_URIS["global_en"])
            .strip()
            .rstrip("/")
        )
        api_path = urlsplit(self.API_URI).path.rstrip("/")
        if api_path.endswith(("/anthropic/v1", "/anthropic/v1/messages")):
            raise ValueError(
                "MINIMAX_API_URI Anthropic base URLs must end in /anthropic"
            )
        self.API_PROTOCOL = "anthropic" if api_path.endswith("/anthropic") else "openai"
        self.MAX_TOKENS = (
            int(MINIMAX_MAX_TOKENS)
            if MINIMAX_MAX_TOKENS
            else MODEL_CONTEXT_WINDOWS.get(self.AI_MODEL, 32_000)
        )
        model_context_window = MODEL_CONTEXT_WINDOWS.get(self.AI_MODEL)
        if self.MAX_TOKENS <= 0:
            raise ValueError("MINIMAX_MAX_TOKENS must be positive")
        if model_context_window and self.MAX_TOKENS > model_context_window:
            raise ValueError(
                f"MINIMAX_MAX_TOKENS exceeds the {self.AI_MODEL} context window"
            )
        self.MAX_OUTPUT_TOKENS = (
            int(MINIMAX_MAX_OUTPUT_TOKENS)
            if MINIMAX_MAX_OUTPUT_TOKENS
            else MODEL_OUTPUT_TOKEN_DEFAULTS.get(self.AI_MODEL, 4096)
        )
        self.AI_TEMPERATURE = float(MINIMAX_TEMPERATURE)
        if not 0 <= self.AI_TEMPERATURE <= 2:
            raise ValueError("MINIMAX_TEMPERATURE must be between 0 and 2")
        self.AI_TOP_P = (
            float(MINIMAX_TOP_P)
            if MINIMAX_TOP_P not in (None, "")
            else MODEL_TOP_P_DEFAULTS.get(self.AI_MODEL, 0.95)
        )
        if not 0 <= self.AI_TOP_P <= 1:
            raise ValueError("MINIMAX_TOP_P must be between 0 and 1")
        if not 0 < self.MAX_OUTPUT_TOKENS <= self.MAX_TOKENS:
            raise ValueError(
                "MINIMAX_MAX_OUTPUT_TOKENS must be positive and fit the context window"
            )

        requested_thinking = str(MINIMAX_THINKING or "").strip().lower()
        if requested_thinking not in ("", "adaptive", "disabled"):
            raise ValueError("MINIMAX_THINKING must be blank, adaptive, or disabled")
        if self.AI_MODEL == "MiniMax-M2.7":
            self.THINKING = "always_on"
        else:
            self.THINKING = requested_thinking or None
        self.SERVICE_TIER = str(MINIMAX_SERVICE_TIER or "standard").strip().lower()
        if self.SERVICE_TIER not in ("standard", "priority"):
            raise ValueError("MINIMAX_SERVICE_TIER must be standard or priority")
        if self.AI_MODEL != "MiniMax-M3" and self.SERVICE_TIER != "standard":
            raise ValueError("Priority service is only available with MiniMax-M3")

        self.WAIT_BETWEEN_REQUESTS = (
            int(MINIMAX_WAIT_BETWEEN_REQUESTS) if MINIMAX_WAIT_BETWEEN_REQUESTS else 0
        )
        self.WAIT_AFTER_FAILURE = (
            int(MINIMAX_WAIT_AFTER_FAILURE) if MINIMAX_WAIT_AFTER_FAILURE else 3
        )
        self.failures = 0
        self.configured = bool(
            self.MINIMAX_API_KEY
            and self.MINIMAX_API_KEY.strip()
            and self.MINIMAX_API_KEY.lower()
            not in ("your_minimax_api_key", "none", "null", "false", "0")
        )
        self.commands = {
            "Generate Response with MiniMax": self.generate_response_command,
        }

        if self.configured:
            self.ApiClient = kwargs.get("ApiClient")

    @staticmethod
    def services():
        return ["llm", "vision"]

    def get_max_tokens(self):
        return self.MAX_TOKENS

    def is_configured(self):
        return self.configured

    async def inference(
        self,
        prompt: str,
        tokens: int = 0,
        images: list = [],
        stream: bool = False,
        use_smartest: bool = False,
    ) -> str:
        if not self.configured:
            raise Exception("MiniMax provider not configured")
        if images and self.AI_MODEL != "MiniMax-M3":
            raise ValueError(f"{self.AI_MODEL} does not support multimodal input")

        messages = []
        if images:
            content = [{"type": "text", "text": prompt}]
            content.extend(
                _media_content_part(media, self.API_PROTOCOL) for media in images
            )
            messages.append({"role": "user", "content": content})
        elif self.API_PROTOCOL == "anthropic":
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            )
        else:
            messages.append({"role": "user", "content": prompt})

        if self.WAIT_BETWEEN_REQUESTS > 0:
            time.sleep(self.WAIT_BETWEEN_REQUESTS)

        payload = {
            "model": self.AI_MODEL,
            "messages": messages,
            "temperature": self.AI_TEMPERATURE,
            "top_p": self.AI_TOP_P,
            "stream": stream,
        }
        if self.API_PROTOCOL == "anthropic":
            payload["max_tokens"] = self.MAX_OUTPUT_TOKENS
            payload["stop_sequences"] = ["</execute>"]
            api_url = f"{self.API_URI}/v1/messages"
            headers = {
                "x-api-key": self.MINIMAX_API_KEY,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "Content-Type": "application/json",
            }
        else:
            payload["max_completion_tokens"] = self.MAX_OUTPUT_TOKENS
            payload["n"] = 1
            payload["stop"] = ["</execute>"]
            api_url = f"{self.API_URI}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.MINIMAX_API_KEY}",
                "Content-Type": "application/json",
            }
        if self.AI_MODEL == "MiniMax-M3":
            if self.THINKING:
                payload["thinking"] = {"type": self.THINKING}
            payload["service_tier"] = self.SERVICE_TIER

        try:
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                stream=stream,
                timeout=300,
            )
            response.raise_for_status()
            self.failures = 0
            if stream:
                if self.API_PROTOCOL == "anthropic":
                    return parse_anthropic_sse_stream(response)
                return parse_sse_stream(response)
            response_data = response.json()
            if self.API_PROTOCOL == "anthropic":
                return "".join(
                    block.get("text", "")
                    for block in response_data.get("content", [])
                    if block.get("type") == "text"
                )
            return response_data["choices"][0]["message"]["content"]
        except Exception as error:
            self.failures += 1
            logging.info(f"MiniMax API error: {error}")
            if self.failures >= 3:
                raise Exception(f"MiniMax API error: too many failures. {error}")
            if self.WAIT_AFTER_FAILURE > 0:
                time.sleep(self.WAIT_AFTER_FAILURE)
            return await self.inference(
                prompt=prompt,
                tokens=tokens,
                images=images,
                stream=stream,
                use_smartest=use_smartest,
            )

    async def generate_response_command(self, prompt: str) -> str:
        """Generate a response with MiniMax."""
        return await self.inference(prompt=prompt)
