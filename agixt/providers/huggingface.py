import requests
import time
import logging

MODELS = {
    "HuggingFaceH4/starchat-beta": 8192,
    "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5": 1512,
    "bigcode/starcoderplus": 8192,
    "bigcode/starcoder": 8192,
    "bigcode/santacoder": 1512,
    "EleutherAI/gpt-neox-20b": 1512,
    "EleutherAI/gpt-neo-1.3B": 2048,
    "RedPajama-INCITE-Instruct-3B-v1": 2048,
}

DEFAULT_MAX_LENGHT = 4096


class HuggingfaceProvider:
    def __init__(
        self,
        MODEL_PATH: str = "HuggingFaceH4/starchat-beta",
        HUGGINGFACE_API_KEY: str = None,
        HUGGINGFACE_API_URL: str = "https://api-inference.huggingface.co/models/{model}",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 1024,
        AI_MODEL: str = "starchat",
        stop=["<|end|>"],
        max_retries: int = 15,
        **kwargs,
    ):
        self.requirements = []
        self.MODEL_PATH = MODEL_PATH
        self.HUGGINGFACE_API_KEY = HUGGINGFACE_API_KEY
        self.HUGGINGFACE_API_URL = HUGGINGFACE_API_URL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.stop = stop
        self.max_retries = max_retries
        self.parameters = kwargs

    def get_url(self) -> str:
        return self.HUGGINGFACE_API_URL.replace("{model}", self.MODEL_PATH)

    def get_max_length(self):
        if self.MODEL_PATH in MODELS:
            return MODELS[self.MODEL_PATH]
        return DEFAULT_MAX_LENGHT

    def get_max_new_tokens(self, input_length: int = 0) -> int:
        return min(self.get_max_length() - input_length, self.MAX_TOKENS)

    def request(self, inputs, **kwargs):
        payload = {"inputs": inputs, "parameters": {**kwargs}}
        headers = {}
        if self.HUGGINGFACE_API_KEY:
            headers["Authorization"] = f"Bearer {self.HUGGINGFACE_API_KEY}"

        tries = 0
        while True:
            tries += 1
            if tries > self.max_retries:
                raise ValueError(f"Reached max retries: {self.max_retries}")
            response = requests.post(self.get_url(), json=payload, headers=headers)
            if response.status_code == 429:
                logging.info(
                    f"Server Error {response.status_code}: Getting rate-limited / wait for {tries} seconds."
                )
                time.sleep(tries)
            elif response.status_code >= 500:
                logging.info(
                    f"Server Error {response.status_code}: {response.json()['error']} / wait for {tries} seconds"
                )
                time.sleep(tries)
            elif response.status_code != 200:
                raise ValueError(f"Error {response.status_code}: {response.text}")
            else:
                break

        content_type = response.headers["Content-Type"]
        if content_type == "application/json":
            return response.json()

    async def instruct(self, prompt, tokens: int = 0):
        result = self.request(
            prompt,
            temperature=self.AI_TEMPERATURE,
            max_new_tokens=self.get_max_new_tokens(tokens),
            return_full_text=False,
            stop=self.stop,
            **self.parameters,
        )[0]["generated_text"]
        if self.stop:
            for stop_seq in self.stop:
                find = result.find(stop_seq)
                if find >= 0:
                    result = result[:find]
        return result


if __name__ == "__main__":
    import asyncio

    async def run_test():
        response = await HuggingfaceProvider().instruct(
            "<|system|>\n<|end|>\n<|user|>\nHello<|end|>\n<|assistant|>\n"
        )
        print(f"Test: {response}")
        response = await HuggingfaceProvider(
            "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", stop=["<|endoftext|>"]
        ).instruct("<|prompter|>Hello<|endoftext|><|assistant|>")
        print(f"Test2: {response}")

    asyncio.run(run_test())
