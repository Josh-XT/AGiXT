import requests


class PetalProvider:
    def __init__(
        self,
        AI_MODEL: str = "stabilityai/StableBeluga2",
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        MAX_TOKENS: int = 1024,
        **kwargs,
    ):
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 1024
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.AI_MODEL = AI_MODEL if AI_MODEL else "stabilityai/StableBeluga2"

    async def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = int(self.MAX_TOKENS) - tokens
        payload = {
            "inputs": prompt,
            "max_new_tokens": max_new_tokens,
            "do_sample": 1,
            "temperature": self.AI_TEMPERATURE,
            "top_p": self.AI_TOP_P,
            "model": self.AI_MODEL,
        }
        response = requests.post(
            url="https://chat.petals.dev/api/v1/generate",
            data=payload,
        )
        response = response.json()
        if response["ok"]:
            return response["output"]
        raise ValueError("No response from Petal API\n" + str(response["traceback"]))


if __name__ == "__main__":
    import asyncio

    async def run_test():
        petal = PetalProvider()
        response = await petal.instruct("What is the meaning of life?")
        print(response)

    asyncio.run(run_test())
