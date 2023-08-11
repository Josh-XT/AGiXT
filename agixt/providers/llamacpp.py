import subprocess
import sys
import os
import logging
import random

try:
    from llama_cpp import Llama
except:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "llama-cpp-python"])
    from llama_cpp import Llama


class LlamacppProvider:
    def __init__(
        self,
        MODEL_PATH: str = "",
        MAX_TOKENS: int = 2048,
        AI_TEMPERATURE: float = 0.7,
        AI_MODEL: str = "default",
        GPU_LAYERS: int = 0,
        BATCH_SIZE: int = 2048,
        THREADS: int = 0,
        STOP_SEQUENCE: str = "</s>",
        **kwargs,
    ):
        self.requirements = ["llama-cpp-python"]
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 2048
        self.AI_MODEL = AI_MODEL if AI_MODEL else "default"
        self.GPU_LAYERS = GPU_LAYERS if GPU_LAYERS else 0
        self.BATCH_SIZE = BATCH_SIZE if BATCH_SIZE else 2048
        self.THREADS = THREADS if THREADS != 0 else None
        self.STOP_SEQUENCE = STOP_SEQUENCE if STOP_SEQUENCE else "</s>"
        self.MODEL_PATH = MODEL_PATH
        if self.MODEL_PATH:
            try:
                self.MAX_TOKENS = int(self.MAX_TOKENS)
            except:
                self.MAX_TOKENS = 2048

    async def instruct(self, prompt, tokens: int = 0):
        if os.path.isfile(self.MODEL_PATH):
            self.model = Llama(
                model_path=self.MODEL_PATH,
                n_gpu_layers=int(self.GPU_LAYERS),
                n_threads=int(self.THREADS),
                n_batch=int(self.BATCH_SIZE),
                n_ctx=int(self.MAX_TOKENS),
                seed=random.randint(1, 1000000000),
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
        try:
            self.model.reset()
        except:
            print("Unable to reset model.")
        return data
