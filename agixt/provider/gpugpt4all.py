import subprocess
import sys

try:
    from nomic.gpt4all import GPT4AllGPU as GPT4All
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "nomic"])
    from nomic.gpt4all import GPT4AllGPU as GPT4All


class Gpugpt4allProvider:
    def __init__(
        self,
        MODEL_PATH: str = "",
        MAX_TOKENS: int = 2000,
        AI_MODEL: str = "default",
        AI_TEMPERATURE: float = 0.7,
        **kwargs,
    ):
        try:
            self.max_tokens = int(MAX_TOKENS)
        except:
            self.max_tokens = 2000
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        # GPT4All will just download the model, maybe save it in our workspace?
        self.model = GPT4All(llama_path=MODEL_PATH)
        self.config = {
            "num_beams": 2,
            "min_new_tokens": 10,
            "max_length": 100,
            "repetition_penalty": 2.0,
        }
        # TODO: Need to reseach to add temperature, no obvious flag.

    def instruct(self, prompt):
        try:
            return self.model.generate(prompt, self.config)
        except Exception as e:
            return f"GPT4ALL Error: {e}"
