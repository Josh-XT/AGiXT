try:
    from llama_cpp import Llama
except:
    print("Failed to import llama-cpp-python.")

import os


class LlamacppProvider:
    def __init__(
        self,
        MODEL_PATH: str = "",
        MAX_TOKENS: int = 2000,
        AI_TEMPERATURE: float = 0.7,
        AI_MODEL: str = "default",
        **kwargs
    ):
        self.requirements = ["llama-cpp-python"]
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL

        if MODEL_PATH:
            try:
                self.MAX_TOKENS = int(self.MAX_TOKENS)
            except:
                self.MAX_TOKENS = 2000

        if os.path.isfile(MODEL_PATH):
            self.model = Llama(model_path=MODEL_PATH, n_ctx=self.MAX_TOKENS * 2)
        else:
            print("Failed to import model - not a file")

    def instruct(self, prompt, tokens: int = 0):
        return self.model(
            prompt,
            max_tokens=self.MAX_TOKENS,
            stop=["\n"],
            temperature=float(self.AI_TEMPERATURE),
        )["choices"][0]["text"]
