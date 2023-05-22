import subprocess
import sys
import os

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
        STOP_SEQUENCE: str = "\n",
        **kwargs
    ):
        self.requirements = ["llama-cpp-python"]
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.GPU_LAYERS = GPU_LAYERS
        self.BATCH_SIZE = BATCH_SIZE
        self.THREADS = THREADS if THREADS != 0 else None
        self.STOP_SEQUENCE = STOP_SEQUENCE

        if MODEL_PATH:
            try:
                self.MAX_TOKENS = int(self.MAX_TOKENS)
            except:
                self.MAX_TOKENS = 2000

        if os.path.isfile(MODEL_PATH):
            self.model = Llama(
                model_path=MODEL_PATH,
                n_ctx=(int(self.MAX_TOKENS) * 2),
                n_gpu_layers=int(self.GPU_LAYERS),
                n_threads=int(self.THREADS),
            )
        else:
            print("Unable to find model path.")

    def instruct(self, prompt, tokens: int = 0):
        max_tokens = int(self.MAX_TOKENS) - tokens
        if max_tokens < 1:
            max_tokens = int(self.MAX_TOKENS)

        return self.model(
            prompt,
            max_tokens=max_tokens,
            stop=[self.STOP_SEQUENCE],
            temperature=float(self.AI_TEMPERATURE),
        )["choices"][0]["text"]
