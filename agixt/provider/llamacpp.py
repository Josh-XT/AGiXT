import subprocess
import sys
import os
import requests

try:
    from llama_cpp import Llama
except:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "llama-cpp-python"])
    from llama_cpp import Llama


# wget https://huggingface.co/NeoDim/starchat-alpha-GGML/blob/main/starchat-alpha-ggml-q5_1.bin
# MODEL_PATH = "./models/starchat/starchat-alpha-ggml-q5_1.bin"
# AI_MODEL = "starchat"
# MAX_TOKENS = 8000
# GPU_LAYERS = 40
# TREADS = 24
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
        else:
            self.MODEL_PATH = "./models/starchat/starchat-alpha-ggml-q5_1.bin"
            print("No model found. Downloading Starchat model...")
            with requests.get(
                "https://huggingface.co/NeoDim/starchat-alpha-GGML/blob/main/starchat-alpha-ggml-q5_1.bin",
                stream=True,
            ) as r:
                r.raise_for_status()
                with open(self.MODEL_PATH, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            self.MAX_TOKENS = 8000

    def instruct(self, prompt, tokens: int = 0):
        max_tokens = int(self.MAX_TOKENS) - tokens
        if max_tokens < 1:
            max_tokens = int(self.MAX_TOKENS)

        if os.path.isfile(self.MODEL_PATH):
            self.model = Llama(
                model_path=self.MODEL_PATH,
                n_ctx=int(self.MAX_TOKENS),
                n_gpu_layers=int(self.GPU_LAYERS),
                n_threads=int(self.THREADS),
            )
        else:
            print("Unable to find model path.")

        return self.model(
            prompt,
            max_tokens=max_tokens,
            stop=[self.STOP_SEQUENCE],
            temperature=float(self.AI_TEMPERATURE),
        )["choices"][0]["text"]
