import time
import logging
import random
import requests
import json
from Globals import getenv


class ChutesProvider:
    """
    This provider uses the Chutes.ai API to generate text from prompts.
    Chutes.ai provides OpenAI-compatible endpoints for deployed models.
    Get your API key from the Chutes dashboard at <https://chutes.ai/app>.

    The Chutes endpoint URL format is: https://{username}-{chute-name}.chutes.ai
    For example: https://myuser-my-llm.chutes.ai
    """

    friendly_name = "Chutes.ai"

    def __init__(
        self,
        CHUTES_API_KEY: str = "",
        CHUTES_ENDPOINT_URL: str = "",
        CHUTES_MODEL: str = "meta-llama/Llama-3.1-8B-Instruct",
        CHUTES_MAX_TOKENS: int = 4096,
        CHUTES_TEMPERATURE: float = 0.7,
        CHUTES_TOP_P: float = 0.9,
        CHUTES_WAIT_BETWEEN_REQUESTS: int = 1,
        CHUTES_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["requests"]
        self.AI_MODEL = (
            CHUTES_MODEL if CHUTES_MODEL else "meta-llama/Llama-3.1-8B-Instruct"
        )
        self.AI_TEMPERATURE = CHUTES_TEMPERATURE if CHUTES_TEMPERATURE else 0.7
        self.AI_TOP_P = CHUTES_TOP_P if CHUTES_TOP_P else 0.9
        self.MAX_TOKENS = CHUTES_MAX_TOKENS if CHUTES_MAX_TOKENS else 4096
        self.ENDPOINT_URL = CHUTES_ENDPOINT_URL if CHUTES_ENDPOINT_URL else ""
        self.WAIT_AFTER_FAILURE = (
            CHUTES_WAIT_AFTER_FAILURE if CHUTES_WAIT_AFTER_FAILURE else 3
        )
        self.WAIT_BETWEEN_REQUESTS = (
            CHUTES_WAIT_BETWEEN_REQUESTS if CHUTES_WAIT_BETWEEN_REQUESTS else 1
        )
        self.API_KEY = CHUTES_API_KEY
        self.FAILURES = []
        self.failures = 0

    @staticmethod
    def services():
        return ["llm", "vision"]

    def rotate_uri(self):
        """Rotate to the next available endpoint URL if multiple are provided"""
        self.FAILURES.append(self.ENDPOINT_URL)
        uri_list = self.ENDPOINT_URL.split(",")
        random.shuffle(uri_list)
        for uri in uri_list:
            if uri not in self.FAILURES:
                self.ENDPOINT_URL = uri
                break

    async def inference(
        self, prompt, tokens: int = 0, images: list = [], stream: bool = False
    ):
        if not self.ENDPOINT_URL:
            return "Please configure the Chutes endpoint URL (e.g., https://myuser-my-llm.chutes.ai) in the Agent Management page."

        if self.API_KEY == "" or self.API_KEY == "YOUR_CHUTES_API_KEY":
            return "Please go to the Agent Management page to set your Chutes API key."

        # Ensure endpoint URL ends with the chat completions path
        base_url = self.ENDPOINT_URL.rstrip("/")
        if not base_url.endswith("/v1/chat/completions"):
            api_url = f"{base_url}/v1/chat/completions"
        else:
            api_url = base_url

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.API_KEY,
        }

        # Build messages
        messages = []
        if len(images) > 0:
            # Vision support - add images to message content
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            )
            for image in images:
                if image.startswith("http"):
                    messages[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image,
                            },
                        }
                    )
                else:
                    # Read local image and convert to base64
                    file_type = image.split(".")[-1]
                    with open(image, "rb") as f:
                        import base64

                        image_base64 = base64.b64encode(f.read()).decode("utf-8")
                    messages[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{file_type};base64,{image_base64}"
                            },
                        }
                    )
        else:
            messages.append({"role": "user", "content": prompt})

        # Build request payload
        payload = {
            "model": self.AI_MODEL,
            "messages": messages,
            "temperature": float(self.AI_TEMPERATURE),
            "max_tokens": int(self.MAX_TOKENS) if tokens == 0 else int(tokens),
            "top_p": float(self.AI_TOP_P),
            "stream": stream,
        }

        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))

        try:
            if stream:
                # Streaming response
                response = requests.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=120,
                )
                response.raise_for_status()

                def stream_generator():
                    for line in response.iter_lines():
                        if line:
                            line_str = line.decode("utf-8").strip()
                            if line_str.startswith("data: "):
                                data = line_str[6:]
                                if data != "[DONE]":
                                    try:
                                        chunk = json.loads(data)
                                        if (
                                            "choices" in chunk
                                            and len(chunk["choices"]) > 0
                                        ):
                                            delta = chunk["choices"][0].get("delta", {})
                                            content = delta.get("content", "")
                                            if content:
                                                yield content
                                    except json.JSONDecodeError:
                                        pass

                return stream_generator()
            else:
                # Non-streaming response
                response = requests.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                response.raise_for_status()
                result = response.json()

                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
                else:
                    return "No response from model"

        except requests.exceptions.RequestException as e:
            logging.error(f"Chutes API Error: {e}")
            self.failures += 1

            if self.failures > 3:
                raise Exception(f"Chutes API Error: Too many failures. {e}")

            if "," in self.ENDPOINT_URL:
                self.rotate_uri()

            if int(self.WAIT_AFTER_FAILURE) > 0:
                time.sleep(int(self.WAIT_AFTER_FAILURE))
                return await self.inference(
                    prompt=prompt, tokens=tokens, images=images, stream=stream
                )

            return f"Error calling Chutes API: {str(e)}"
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            return f"Unexpected error: {str(e)}"
