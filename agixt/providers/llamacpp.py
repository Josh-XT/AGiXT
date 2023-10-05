import requests
import random


# Instructions for setting up llama.cpp server:
# https://github.com/ggerganov/llama.cpp/tree/master/examples/server#llamacppexampleserver
class LlamacppProvider:
    def __init__(
        self,
        AI_PROVIDER_URI: str = "http://localhost:8000",
        AI_MODEL: str = "default",
        PROMPT_PREFIX: str = "",
        PROMPT_SUFFIX: str = "",
        STOP_SEQUENCE: str = "</s>",
        MAX_TOKENS: int = 4096,
        AI_TEMPERATURE: float = 0.8,
        AI_TOP_P: float = 0.95,
        AI_TOP_K: int = 40,
        TFS_Z: float = 1.0,
        TYPICAL_P: float = 1.0,
        REPEAT_PENALTY: float = 1.1,
        REPEAT_LAST_N: int = 64,
        PENALIZE_NL: bool = True,
        PRESENCE_PENALTY: float = 0.0,
        FREQUENCY_PENALTY: float = 0.0,
        MIROSTAT: int = 0,
        MIROSTAT_TAU: float = 5.0,
        MIROSTAT_ETA: float = 0.1,
        IGNORE_EOS: bool = False,
        LOGIT_BIAS: list = [],
        **kwargs,
    ):
        self.AI_PROVIDER_URI = (
            AI_PROVIDER_URI if AI_PROVIDER_URI else "http://localhost:8000"
        )
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.AI_TOP_K = AI_TOP_K if AI_TOP_K else 40
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 2048
        self.AI_MODEL = AI_MODEL if AI_MODEL else "default"
        self.STOP_SEQUENCE = STOP_SEQUENCE if STOP_SEQUENCE else "</s>"
        self.MAX_TOKENS = int(self.MAX_TOKENS) if self.MAX_TOKENS else 2048
        self.TFS_Z = TFS_Z if TFS_Z else 1.0
        self.TYPICAL_P = TYPICAL_P if TYPICAL_P else 1.0
        self.REPEAT_PENALTY = REPEAT_PENALTY if REPEAT_PENALTY else 1.1
        self.REPEAT_LAST_N = REPEAT_LAST_N if REPEAT_LAST_N else 64
        self.PENALIZE_NL = PENALIZE_NL if PENALIZE_NL else True
        self.PRESENCE_PENALTY = PRESENCE_PENALTY if PRESENCE_PENALTY else 0.0
        self.FREQUENCY_PENALTY = FREQUENCY_PENALTY if FREQUENCY_PENALTY else 0.0
        self.MIROSTAT = MIROSTAT if MIROSTAT else 0
        self.MIROSTAT_TAU = MIROSTAT_TAU if MIROSTAT_TAU else 5.0
        self.MIROSTAT_ETA = MIROSTAT_ETA if MIROSTAT_ETA else 0.1
        self.IGNORE_EOS = IGNORE_EOS if IGNORE_EOS else False
        self.LOGIT_BIAS = LOGIT_BIAS if LOGIT_BIAS else []
        self.PROMPT_PREFIX = PROMPT_PREFIX if PROMPT_PREFIX else ""
        self.PROMPT_SUFFIX = PROMPT_SUFFIX if PROMPT_SUFFIX else ""

    async def instruct(self, prompt, tokens: int = 0):
        max_tokens = int(self.MAX_TOKENS) - tokens
        prompt = f"{self.PROMPT_PREFIX}{prompt}{self.PROMPT_SUFFIX}"
        params = {
            "prompt": prompt,
            "temperature": float(self.AI_TEMPERATURE),
            "top_p": float(self.AI_TOP_P),
            "stop": self.STOP_SEQUENCE,
            "seed": random.randint(1, 1000000000),
            "n_predict": int(max_tokens),
            "stream": False,
            "top_k": int(self.AI_TOP_K),
            "tfs_z": float(self.TFS_Z),
            "typical_p": float(self.TYPICAL_P),
            "repeat_penalty": float(self.REPEAT_PENALTY),
            "repeat_last_n": int(self.REPEAT_LAST_N),
            "penalize_nl": self.PENALIZE_NL,
            "presence_penalty": float(self.PRESENCE_PENALTY),
            "frequency_penalty": float(self.FREQUENCY_PENALTY),
            "mirostat": int(self.MIROSTAT),
            "mirostat_tau": float(self.MIROSTAT_TAU),
            "mirostat_eta": float(self.MIROSTAT_ETA),
            "ignore_eos": self.IGNORE_EOS,
            "logit_bias": self.LOGIT_BIAS,
        }
        response = requests.post(f"{self.AI_PROVIDER_URI}/completion", json=params)
        data = response.json()
        print(data)
        if "choices" in data:
            choices = data["choices"]
            if choices:
                return choices[0]["text"]
        if "content" in data:
            return data["content"]
        return data
