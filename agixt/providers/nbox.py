import requests


class NBoxProvider:
    def __init__(self,
                 AI_TEMPERATURE: float = 0.7,
                 MAX_TOKENS: int = 1024,
                 NBOX_TOKEN: str = "",
                 AI_MODEL: str = "llama-2-chat-70b-4k",
                 ):
        self.url = "https://chat.nbox.ai/api/chat/completions"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 1024
        self.AI_MODEL = AI_MODEL if AI_MODEL else "llama-2-chat-70b-4k"
        self.headers = {
            "Authorization": NBOX_TOKEN,
            "Content-Type": "application/json"
        }
        self.data = {
            "temperature": self.AI_TEMPERATURE,
            "messages": [
                {
                    "role": "system",
                    "content": "You are ChatNBX"
                },
                {
                    "role": "user",
                    "content": "Who are you?"
                }
            ],
            "model": AI_MODEL.lower(),
            "stream": False,
            "max_tokens": 1000
        }

    async def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = int(self.MAX_TOKENS) - tokens
        self.data["messages"][1]["content"] = prompt
        self.data["max_tokens"] = max_new_tokens
        response = requests.post(self.url, headers=self.headers, json=self.data)
        response = response.json()
        if "error" in response:
            return "Error: " + response["error"]
        return response["choices"][0]["message"]['content']


if __name__ == "__main__":
    import asyncio
    my_token = ""

    async def run_test():
        nbox = NBoxProvider(NBOX_TOKEN=my_token)
        response = await nbox.instruct("Hello")
        print(response)

    asyncio.run(run_test())
