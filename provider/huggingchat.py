import time
from requests.sessions import Session
from provider import max_tokens_ceiling


class HuggingchatProvider:
    def __init__(
        self,
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 2000,
        AI_MODEL: str = "openassistant",
        **kwargs,
    ):
        self.requirements = []
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS_CEILING = max_tokens_ceiling(AI_MODEL)
        self.MAX_TOKENS = (
            MAX_TOKENS
            if MAX_TOKENS <= self.MAX_TOKENS_CEILING
            else self.MAX_TOKENS_CEILING
        )
        self.AI_MODEL = AI_MODEL

    def instruct(self, prompt: str, tokens: int = 0) -> str:
        session = Session()
        session.get(url="https://huggingface.co/chat/")
        res = session.post(
            url="https://huggingface.co/chat/settings",
            data={"ethicsModalAccepted": True},
        )
        assert res.status_code == 200, "Failed to accept ethics modal"

        res = session.post(
            url="https://huggingface.co/chat/conversation",
            json={"model": self._get_model_name(self.AI_MODEL)},
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 200, "Failed to create new conversation"

        conversation_id = res.json()["conversationId"]
        url = f"https://huggingface.co/chat/conversation/{conversation_id}"
        max_new_tokens = int(self.MAX_TOKENS) - tokens

        # Huggingchat max limit is 1904, discovered via trial and error.
        if max_new_tokens > 1904:
            max_new_tokens = 1904

        res = session.post(
            url=url,
            json={
                "inputs": prompt,
                "parameters": {
                    "temperature": float(self.AI_TEMPERATURE),
                    "top_p": 0.95,
                    "repetition_penalty": 1.2,
                    "top_k": 50,
                    "truncate": 1024,
                    "watermark": False,
                    "max_new_tokens": max_new_tokens,
                    "stop": ["<|endoftext|>"],
                    "return_full_text": False,
                },
                "stream": False,
                "options": {"use_cache": False},
            },
            stream=False,
        )
        try:
            data = res.json()
            data = data[0] if data else {}
        except ValueError:
            print("Invalid JSON response")
            data = {}
        except:
            if data.get("error_type", None) == "overloaded":
                print(
                    "Provider says that it is overloaded, waiting 3 seconds and trying again"
                )
                # @Note: if this is kept in the repo, the delay should be configurable
                time.sleep(3)
                return self.instruct(prompt)
            else:
                print("Unknown error")
                print(res.text)
                data = {}

        return data.get("generated_text", "")

    def _get_model_name(self, ai_model: str):
        """Returns a model name based on the AI_MODEL"""

        if ai_model == "openassistant":
            model_name = "OpenAssistant/oasst-sft-6-llama-30b-xor"
        elif ai_model == "starcoderbase":
            model_name = "bigcode/starcoderbase"
        return model_name
