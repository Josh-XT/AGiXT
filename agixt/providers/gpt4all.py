import subprocess
import sys

try:
    from gpt4all import GPT4All
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "gpt4all"])
    from gpt4all import GPT4All


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
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 2000
        self.AI_MODEL = AI_MODEL if AI_MODEL else "default"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        # TODO: Need to research to add temperature, no obvious flag.

    async def instruct(self, prompt):
        try:
            return self.model.prompt(prompt)
        except Exception as e:
            return f"GPT4ALL Error: {e}"
