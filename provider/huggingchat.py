from Config import Config
from requests.sessions import Session

CFG = Config()


class AIProvider:
    def __init__(self):
        self.settings = [
            "MAX_TOKENS",
            "AI_TEMPERATURE",
        ]
        self.requirements = []

    def instruct(self, prompt: str) -> str:
        session = Session()
        session.get(url="https://huggingface.co/chat/")
        res = session.post(url="https://huggingface.co/chat/conversation")
        assert res.status_code == 200, "Failed to create new conversation"
        conversation_id = res.json()["conversationId"]
        url = f"https://huggingface.co/chat/conversation/{conversation_id}"
        max_tokens = int(CFG.MAX_TOKENS) - len(prompt)

        if max_tokens > 1904:
            max_tokens = 1904

        res = session.post(
            url=url,
            json={
                "inputs": prompt,
                "parameters": {
                    "temperature": float(CFG.AI_TEMPERATURE),
                    "top_p": 0.95,
                    "repetition_penalty": 1.2,
                    "top_k": 50,
                    "truncate": 1024,
                    "watermark": False,
                    "max_new_tokens": max_tokens,
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
        except ValueError:
            print("Invalid JSON response")
            data = {}

        data = data[0] if data else {}
        return data.get("generated_text", "")
