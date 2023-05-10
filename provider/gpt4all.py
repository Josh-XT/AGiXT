from pathlib import Path

try:
    from nomic.gpt4all import GPT4All
except ImportError:
    print("Failed to import gpt4all.")


class Gpt4allProvider:
    def __init__(
        self,
        MODEL_NAME: str = "gpt4all-lora-quantized",
        MAX_TOKENS: int = 2000,
        AI_MODEL: str = "default",
        AI_TEMPERATURE: float = 0.7,
        **kwargs,
    ):
        self.model = GPT4All(model=MODEL_NAME)
        self.model.open()
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        # TODO: Need to research to add temperature, no obvious flag.

    def instruct(self, prompt):
        try:
            return self.model.prompt(prompt)
        except Exception as e:
            return f"GPT4ALL Error: {e}"
