import time
import logging
import random
import requests
import json


class DeepinfraProvider:
    """
    This provider uses the DeepInfra API to generate text from prompts.
    DeepInfra provides OpenAI-compatible endpoints for deployed models.
    Get your API key from the DeepInfra dashboard at <https://deepinfra.com>.
    """

    def __init__(
        self,
        DEEPINFRA_API_KEY: str = "",
        DEEPINFRA_ENDPOINT_URL: str = "https://api.deepinfra.com/v1/openai",
        DEEPINFRA_MODEL: str = "Qwen/Qwen3-235B-A22B-Instruct-2507",
        DEEPINFRA_VISION_MODEL: str = "Qwen/Qwen3-VL-30B-A3B-Instruct",
        DEEPINFRA_CODING_MODEL: str = "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        DEEPINFRA_MAX_TOKENS: int = 128000,
        DEEPINFRA_TEMPERATURE: float = 0.7,
        DEEPINFRA_TOP_P: float = 0.9,
        DEEPINFRA_WAIT_BETWEEN_REQUESTS: int = 1,
        DEEPINFRA_WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = []
        self.friendly_name = "DeepInfra"
        self.AI_MODEL = (
            DEEPINFRA_MODEL if DEEPINFRA_MODEL else "Qwen/Qwen3-VL-235B-A22B-Instruct"
        )
        self.DEEPINFRA_VISION_MODEL = (
            DEEPINFRA_VISION_MODEL
            if DEEPINFRA_VISION_MODEL
            else "Qwen/Qwen3-VL-235B-A22B-Instruct"
        )
        self.DEEPINFRA_CODING_MODEL = (
            DEEPINFRA_CODING_MODEL
            if DEEPINFRA_CODING_MODEL
            else "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8"
        )
        self.AI_TEMPERATURE = DEEPINFRA_TEMPERATURE if DEEPINFRA_TEMPERATURE else 0.7
        self.AI_TOP_P = DEEPINFRA_TOP_P if DEEPINFRA_TOP_P else 0.9
        self.MAX_TOKENS = DEEPINFRA_MAX_TOKENS if DEEPINFRA_MAX_TOKENS else 128000
        self.ENDPOINT_URL = (
            DEEPINFRA_ENDPOINT_URL
            if DEEPINFRA_ENDPOINT_URL
            else "https://api.deepinfra.com/v1/openai"
        )
        self.WAIT_AFTER_FAILURE = (
            DEEPINFRA_WAIT_AFTER_FAILURE if DEEPINFRA_WAIT_AFTER_FAILURE else 3
        )
        self.WAIT_BETWEEN_REQUESTS = (
            DEEPINFRA_WAIT_BETWEEN_REQUESTS if DEEPINFRA_WAIT_BETWEEN_REQUESTS else 1
        )
        self.DEEPINFRA_API_KEY = DEEPINFRA_API_KEY
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
        self,
        prompt,
        tokens: int = 0,
        images: list = [],
        stream: bool = False,
        use_smartest: bool = False,
    ):
        if (
            self.DEEPINFRA_API_KEY == ""
            or self.DEEPINFRA_API_KEY == "YOUR_DEEPINFRA_API_KEY"
        ):
            return (
                "Please go to the Agent Management page to set your Deepinfra API key."
            )
        if use_smartest:
            self.AI_MODEL = self.DEEPINFRA_CODING_MODEL
        if len(images) > 0:
            self.AI_MODEL = self.DEEPINFRA_VISION_MODEL
        # Ensure endpoint URL ends with the chat completions path
        base_url = self.ENDPOINT_URL.rstrip("/")
        if not base_url.endswith("/chat/completions"):
            api_url = f"{base_url}/chat/completions"
        else:
            api_url = base_url

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.DEEPINFRA_API_KEY}",
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
            logging.error(f"Deepinfra API Error: {e}")
            self.failures += 1

            if self.failures > 3:
                raise Exception(f"Deepinfra API Error: Too many failures. {e}")

            if "," in self.ENDPOINT_URL:
                self.rotate_uri()

            if int(self.WAIT_AFTER_FAILURE) > 0:
                time.sleep(int(self.WAIT_AFTER_FAILURE))
                return await self.inference(
                    prompt=prompt,
                    tokens=tokens,
                    images=images,
                    stream=stream,
                    use_smartest=use_smartest,
                )

            return f"Error calling Deepinfra API: {str(e)}"
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            return f"Unexpected error: {str(e)}"
