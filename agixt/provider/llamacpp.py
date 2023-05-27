import subprocess
import sys
import os
import logging

try:
    from llama_cpp import Llama
except:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "llama-cpp-python"])
    from llama_cpp import Llama


class LlamacppProvider:
    def __init__(
        self,
        MODEL_PATH: str = "",
        MAX_TOKENS: int = 2000,
        AI_TEMPERATURE: float = 0.7,
        AI_MODEL: str = "default",
        GPU_LAYERS: int = 0,
        BATCH_SIZE: int = 512,
        THREADS: int = 0,
        STOP_SEQUENCE: str = "</s>",
        **kwargs,
    ):
        self.requirements = ["llama-cpp-python"]
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.GPU_LAYERS = GPU_LAYERS
        self.BATCH_SIZE = BATCH_SIZE
        self.THREADS = THREADS if THREADS != 0 else None
        self.STOP_SEQUENCE = STOP_SEQUENCE
        self.MODEL_PATH = MODEL_PATH
        if self.MODEL_PATH:
            try:
                self.MAX_TOKENS = int(self.MAX_TOKENS)
            except:
                self.MAX_TOKENS = 2000

    def instruct(self, prompt, tokens: int = 0):
        max_tokens = int(self.MAX_TOKENS) - tokens
        if max_tokens < 1:
            max_tokens = int(self.MAX_TOKENS)
        if os.path.isfile(self.MODEL_PATH):
            self.model = Llama(
                model_path=self.MODEL_PATH,
                n_gpu_layers=int(self.GPU_LAYERS),
                n_threads=int(self.THREADS),
                n_ctx=max_tokens,
            )
        else:
            logging.info("Unable to find model path.")
            return None
        response = self.model(
            prompt,
            stop=[self.STOP_SEQUENCE],
            temperature=float(self.AI_TEMPERATURE),
            echo=True,
        )
        data = response["choices"][0]["text"]
        data = data.replace(prompt, "")
        data = data.lstrip("\n")
        return data
