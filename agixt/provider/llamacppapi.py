import requests

# Llamacpp API Server
# ./server --model "/path/to/ggml-model.bin" --ctx_size 2048 --ngl 32 -port 7171
# Embedding server
# ./server --model "/path/to/ggml-model.bin" --ctx_size 2048 --ngl 32 -port 7172 --embedding

# ctx_size is max tokens
# ngl is is GPU Layers.  Supposedly this works well for an RTX 3080.

# If using the settings above, use the following in your agent settings:
# AI_PROVIDER_URI = "http://localhost:7171"
# EMBEDDING_URI = "http://localhost:7172"


class LlamacppapiProvider:
    def __init__(
        self,
        AI_PROVIDER_URI: str = "http://localhost:7171",
        EMBEDDING_URI: str = "http://localhost:7172",
        MAX_TOKENS: int = 2000,
        AI_TEMPERATURE: float = 0.7,
        AI_MODEL: str = "default",
        BATCH_SIZE: int = 512,
        THREADS: int = 0,
        STOP_SEQUENCE: str = "\n",
        EXCLUDE_STRING: str = "",
        **kwargs,
    ):
        self.AI_PROVIDER_URI = AI_PROVIDER_URI
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.BATCH_SIZE = BATCH_SIZE
        self.THREADS = THREADS if THREADS != 0 else None
        self.STOP_SEQUENCE = STOP_SEQUENCE
        self.EXCLUDE_STRING = EXCLUDE_STRING
        self.EMBEDDING_URI = EMBEDDING_URI
        self.MAX_TOKENS = int(self.MAX_TOKENS)

    def instruct(self, prompt, tokens: int = 0):
        new_tokens = int(self.MAX_TOKENS) - tokens
        params = {
            "prompt": prompt,
            "batch_size": int(self.BATCH_SIZE),
            "temperature": float(self.AI_TEMPERATURE),
            "stop": self.STOP_SEQUENCE,
            "exclude": self.EXCLUDE_STRING,
            "n_predict": new_tokens,
            "threads": int(self.THREADS),
            "interactive": False,
        }
        response = requests.post(f"{self.AI_PROVIDER_URI}/completion", json=params)
        data = response.json()
        return data["content"]

    def embeddding(self, prompt):
        data = requests.post(
            f"{self.EMBEDDING_URI}/embeddding",
            json={"content": prompt, "threads": int(self.THREADS)},
        )
        return data["embedding"]
