import requests
import re


class OobaboogaProvider:
    def __init__(
        self,
        AI_PROVIDER_URI: str = "",
        MAX_TOKENS: int = 2000,
        DO_SAMPLE: str = "True",
        AI_TEMPERATURE: float = 0.7,
        TOP_P: float = 0.9,
        TYPICAL_P: float = 0.2,
        EPSILON_CUTOFF: float = 0,
        ETA_CUTOFF: float = 0,
        TFS: float = 1,
        TOP_A: float = 0,
        REPETITION_PENALTY: float = 1.05,
        ENCODER_REPETITION_PENALTY: float = 1,
        TOP_K: int = 200,
        MIN_LENGTH: float = 0,
        NO_REPEAT_NGRAM_SIZE: float = 0,
        NUM_BEAMS: int = 1,
        PENALTY_ALPHA: float = 0,
        LENGTH_PENALTY: float = 1,
        MIROSTAT_MODE: float = 0,
        MIROSTAT_TAU: float = 5,
        MIROSTAT_ETA: float = 0.1,
        TRUNCATION_LENGTH: int = 2048,
        AI_MODEL: str = "default",
        PROMPT_PREFIX: str = "",
        PROMPT_SUFFIX: str = "",
        **kwargs,
    ):
        self.AI_PROVIDER_URI = AI_PROVIDER_URI
        self.MAX_TOKENS = MAX_TOKENS
        self.DO_SAMPLE = DO_SAMPLE
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.AI_MODEL = AI_MODEL
        self.TOP_P = TOP_P
        self.TYPICAL_P = TYPICAL_P
        self.EPSILON_CUTOFF = EPSILON_CUTOFF
        self.ETA_CUTOFF = ETA_CUTOFF
        self.TFS = TFS
        self.TOP_A = TOP_A
        self.REPETITION_PENALTY = REPETITION_PENALTY
        self.ENCODER_REPETITION_PENALTY = ENCODER_REPETITION_PENALTY
        self.TOP_K = TOP_K
        self.MIN_LENGTH = MIN_LENGTH
        self.NO_REPEAT_NGRAM_SIZE = NO_REPEAT_NGRAM_SIZE
        self.NUM_BEAMS = NUM_BEAMS
        self.PENALTY_ALPHA = PENALTY_ALPHA
        self.LENGTH_PENALTY = LENGTH_PENALTY
        self.MIROSTAT_MODE = MIROSTAT_MODE
        self.MIROSTAT_TAU = MIROSTAT_TAU
        self.MIROSTAT_ETA = MIROSTAT_ETA
        self.TRUNCATION_LENGTH = TRUNCATION_LENGTH
        self.PROMPT_PREFIX = PROMPT_PREFIX
        self.PROMPT_SUFFIX = PROMPT_SUFFIX
        self.requirements = []

    async def instruct(self, prompt, tokens: int = 0):
        new_tokens = int(self.MAX_TOKENS) - tokens
        prompt = f"{self.PROMPT_PREFIX}{prompt}{self.PROMPT_SUFFIX}"
        params = {
            "prompt": prompt,
            "max_new_tokens": new_tokens,
            "do_sample": True,
            "temperature": float(self.AI_TEMPERATURE),
            "top_p": float(self.TOP_P),
            "typical_p": float(self.TYPICAL_P),
            "epsilon_cutoff": float(self.EPSILON_CUTOFF),
            "eta_cutoff": float(self.ETA_CUTOFF),
            "tfs": float(self.TFS),
            "top_a": float(self.TOP_A),
            "repetition_penalty": float(self.REPETITION_PENALTY),
            "encoder_repetition_penalty": float(self.ENCODER_REPETITION_PENALTY),
            "top_k": int(self.TOP_K),
            "min_length": float(self.MIN_LENGTH),
            "no_repeat_ngram_size": float(self.NO_REPEAT_NGRAM_SIZE),
            "num_beams": int(self.NUM_BEAMS),
            "penalty_alpha": float(self.PENALTY_ALPHA),
            "length_penalty": float(self.LENGTH_PENALTY),
            "early_stopping": False,
            "mirostat_mode": float(self.MIROSTAT_MODE),
            "mirostat_tau": float(self.MIROSTAT_TAU),
            "mirostat_eta": float(self.MIROSTAT_ETA),
            "seed": -1,
            "add_bos_token": True,
            "truncation_length": 2048,
            "ban_eos_token": False,
            "skip_special_tokens": True,
            "custom_stopping_strings": "",  # leave this blank
            "stopping_strings": [],
        }
        response = requests.post(f"{self.AI_PROVIDER_URI}/api/v1/generate", json=params)
        data = None

        if response.status_code == 200:
            data = response.json()["results"][0]["text"]
            data = re.sub(r"(?<!\\)\\(?!n)", "", data)

        return data
