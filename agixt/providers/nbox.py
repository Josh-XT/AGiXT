import requests


class NboxProvider:
    def __init__(
        self,
        NBOX_TOKEN: str = "",
        AI_MODEL: str = "llama-2-chat-70b-4k",
        MAX_TOKENS: int = 4085,
        AI_TEMPERATURE: float = 0.7,
        **kwargs,
    ):
        self.NBOX_TOKEN = NBOX_TOKEN
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 4085
        self.AI_MODEL = AI_MODEL.lower() if AI_MODEL else "llama-2-chat-70b-4k"

    async def inference(self, prompt, tokens: int = 0):
        max_new_tokens = int(self.MAX_TOKENS) - tokens
        if max_new_tokens < 0:
            raise Exception(f"Max tokens exceeded: {max_new_tokens}")
        elif max_new_tokens > 4085:
            max_new_tokens = 4085
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
