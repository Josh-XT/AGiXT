import logging
import time
import requests


class RunpodProvider:
    def __init__(
        self,
        API_KEY: str = "",
        AI_PROVIDER_URI: str = "",
        AI_MODEL: str = "default",
        PROMPT_PREFIX: str = "",
        PROMPT_SUFFIX: str = "",
        STOP_STRING: str = "</s>",
        MAX_TOKENS: int = 2048,
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
        **kwargs,
    ):
        self.AI_PROVIDER_URI = (
            AI_PROVIDER_URI if AI_PROVIDER_URI else "https://api.runpod.io"
        )

        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 2048
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_MODEL = AI_MODEL if AI_MODEL else "default"
        self.TOP_P = TOP_P if TOP_P else 0.9
        self.TYPICAL_P = TYPICAL_P if TYPICAL_P else 0.2
        self.EPSILON_CUTOFF = EPSILON_CUTOFF if EPSILON_CUTOFF else 0
        self.ETA_CUTOFF = ETA_CUTOFF if ETA_CUTOFF else 0
        self.TFS = TFS if TFS else 1
        self.TOP_A = TOP_A if TOP_A else 0
        self.REPETITION_PENALTY = REPETITION_PENALTY if REPETITION_PENALTY else 1.05
        self.ENCODER_REPETITION_PENALTY = (
            ENCODER_REPETITION_PENALTY if ENCODER_REPETITION_PENALTY else 1
        )
        self.TOP_K = TOP_K if TOP_K else 200
        self.MIN_LENGTH = MIN_LENGTH if MIN_LENGTH else 0
        self.NO_REPEAT_NGRAM_SIZE = NO_REPEAT_NGRAM_SIZE if NO_REPEAT_NGRAM_SIZE else 0
        self.NUM_BEAMS = NUM_BEAMS if NUM_BEAMS else 1
        self.PENALTY_ALPHA = PENALTY_ALPHA if PENALTY_ALPHA else 0
        self.LENGTH_PENALTY = LENGTH_PENALTY if LENGTH_PENALTY else 1
        self.MIROSTAT_MODE = MIROSTAT_MODE if MIROSTAT_MODE else 0
        self.MIROSTAT_TAU = MIROSTAT_TAU if MIROSTAT_TAU else 5
        self.MIROSTAT_ETA = MIROSTAT_ETA if MIROSTAT_ETA else 0.1
        self.PROMPT_PREFIX = PROMPT_PREFIX if PROMPT_PREFIX else ""
        self.PROMPT_SUFFIX = PROMPT_SUFFIX if PROMPT_SUFFIX else ""
        self.STOP_STRING = STOP_STRING if STOP_STRING else "</s>"
        self.API_KEY = API_KEY
        self.requirements = []

    async def instruct(self, prompt, tokens: int = 0):
        headers = {"Authorization": f"Bearer {self.API_KEY}"}
        new_tokens = int(self.MAX_TOKENS) - tokens

        logging.info("Instructing Agent with %s", prompt)

        run_response = requests.post(
            f"{self.AI_PROVIDER_URI}/run",
            headers=headers,
            json={
                "input": {
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
                    "encoder_repetition_penalty": float(
                        self.ENCODER_REPETITION_PENALTY
                    ),
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
                    "truncation_length": int(self.MAX_TOKENS),
                    "ban_eos_token": False,
                    "skip_special_tokens": True,
                    "custom_stopping_strings": "",  # leave this blank
                    "stopping_strings": [self.STOP_STRING],
                }
            },
        )

        logging.info("Run Response: %s", run_response.json())
        jobId = run_response.json()["id"]
        logging.info("Job ID: %s", jobId)

        while True:
            status_url = f"{self.AI_PROVIDER_URI}/status/{jobId}"
            logging.info("Requesting status url: %s", status_url)
            status_response = requests.get(status_url, headers=headers)
            logging.info("Status Response: %s", status_response.json())
            status = status_response.json()["status"]
            logging.info("Status: %s", status)
            # IN_QUEUE, RUNNING, COMPLETED, FAILED
            if status == "COMPLETED":
                output = status_response.json()["output"]
                logging.info("Output: %s", output)
                return output
            elif status == "FAILED":
                logging.info("JOB FAILED - NEEDS HANDLING")
                return None
            else:
                logging.info("Sleeping for 2")
                time.sleep(2)
