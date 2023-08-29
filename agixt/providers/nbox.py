import requests


class NboxProvider:
    def __init__(
        self,
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4096,
        NBOX_TOKEN: str = "",
        AI_MODEL: str = "llama-2-chat-70b-4k",
    ):
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 4096
        self.AI_MODEL = AI_MODEL.lower() if AI_MODEL else "llama-2-chat-70b-4k"
        self.NBOX_TOKEN = NBOX_TOKEN

    async def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = int(self.MAX_TOKENS) - tokens
        params = {
            "messages": [{"role": "user", "content": prompt}],
            "model": self.AI_MODEL,
            "temperature": float(self.AI_TEMPERATURE),
            "stream": False,
            "max_tokens": max_new_tokens,
        }
        response = requests.post(
            "https://chat.nbox.ai/api/chat/completions",
            headers={
                "Authorization": self.NBOX_TOKEN,
                "Content-Type": "application/json",
            },
            json=params,
        )
        response = response.json()
        if "error" in response:
            return "Error: " + response["error"]
        return response["choices"][0]["message"]["content"]
