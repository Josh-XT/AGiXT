import requests
from typing import Dict, List, Optional


class KoboldProvider:
    def __init__(
        self,
        PROMPT_PREFIX: str = "",
        PROMPT_SUFFIX: str = "",
        AI_PROVIDER_URI: str = "",
        AI_MODEL: str = "default",
        MAX_CONTEXT_LENGTH: Optional[int] = None,
        MAX_LENGTH: Optional[int] = None,
        QUIET: bool = False,
        REP_PEN: float = 1.1,
        REP_PEN_RANGE: int = 320,
        REP_PEN_SLOPE: Optional[int] = None,
        SAMPLER_ORDER: Optional[List[int]] = None,
        SAMPLER_SEED: Optional[int] = None,
        SAMPLER_FULL_DETERMINISM: bool = False,
        STOP_SEQUENCE: Optional[List[str]] = None,
        TEMPERATURE: float = 0.7,
        TFS: float = 1,
        TOP_A: float = 0,
        TOP_K: int = 100,
        TOP_P: float = 0.92,
        MIN_P: float = 0,
        TYPICAL: float = 1,
        USE_DEFAULT_BADWORDSIDS: bool = False,
        MIROSTAT: int = 0,
        MIROSTAT_TAU: float = 5.0,
        MIROSTAT_ETA: float = 0.1,
        GRAMMAR: str = "",
        GRAMMAR_RETAIN_STATE: bool = False,
        DISABLE_INPUT_FORMATTING: bool = True,
        DISABLE_OUTPUT_FORMATTING: bool = True,
        FRMTADSNSP: bool = False,
        FRMTRMBLLN: bool = False,
        FRMTRMSPCH: bool = False,
        FRMTTRIMINC: bool = False,
        SINGLELINE: bool = False,
        **kwargs,
    ):
        self.requirements = []
        self.AI_PROVIDER_URI = (
            AI_PROVIDER_URI if AI_PROVIDER_URI else "http://host.docker.internal:5001"
        )
        self.AI_MODEL = AI_MODEL if AI_MODEL else "default"
        self.PROMPT_PREFIX = PROMPT_PREFIX if PROMPT_PREFIX else ""
        self.PROMPT_SUFFIX = PROMPT_SUFFIX if PROMPT_SUFFIX else ""
        self.MAX_CONTEXT_LENGTH = MAX_CONTEXT_LENGTH if MAX_CONTEXT_LENGTH else None
        self.MAX_LENGTH = MAX_LENGTH if MAX_LENGTH else None
        self.QUIET = QUIET if QUIET else False
        self.REP_PEN = REP_PEN if REP_PEN else 1.1
        self.REP_PEN_RANGE = REP_PEN_RANGE if REP_PEN_RANGE else 320
        self.REP_PEN_SLOPE = REP_PEN_SLOPE if REP_PEN_SLOPE else None
        self.SAMPLER_ORDER = SAMPLER_ORDER if SAMPLER_ORDER else None
        self.SAMPLER_SEED = SAMPLER_SEED if SAMPLER_SEED else None
        self.SAMPLER_FULL_DETERMINISM = (
            SAMPLER_FULL_DETERMINISM if SAMPLER_FULL_DETERMINISM else False
        )
        self.STOP_SEQUENCE = STOP_SEQUENCE if STOP_SEQUENCE else None
        self.TEMPERATURE = TEMPERATURE if TEMPERATURE else 0.7
        self.TFS = TFS if TFS else 1
        self.TOP_A = TOP_A if TOP_A else 0
        self.TOP_K = TOP_K if TOP_K else 100
        self.TOP_P = TOP_P if TOP_P else 0.92
        self.MIN_P = MIN_P if MIN_P else 0
        self.TYPICAL = TYPICAL if TYPICAL else 1
        self.USE_DEFAULT_BADWORDSIDS = (
            USE_DEFAULT_BADWORDSIDS if USE_DEFAULT_BADWORDSIDS else False
        )
        self.MIROSTAT = MIROSTAT if MIROSTAT else 0
        self.MIROSTAT_TAU = MIROSTAT_TAU if MIROSTAT_TAU else 5.0
        self.MIROSTAT_ETA = MIROSTAT_ETA if MIROSTAT_ETA else 0.1
        self.GRAMMAR = GRAMMAR if GRAMMAR else ""
        self.GRAMMAR_RETAIN_STATE = (
            GRAMMAR_RETAIN_STATE if GRAMMAR_RETAIN_STATE else False
        )
        self.DISABLE_INPUT_FORMATTING = (
            DISABLE_INPUT_FORMATTING if DISABLE_INPUT_FORMATTING else True
        )
        self.DISABLE_OUTPUT_FORMATTING = (
            DISABLE_OUTPUT_FORMATTING if DISABLE_OUTPUT_FORMATTING else True
        )
        self.FRMTADSNSP = FRMTADSNSP if FRMTADSNSP else False
        self.FRMTRMBLLN = FRMTRMBLLN if FRMTRMBLLN else False
        self.FRMTRMSPCH = FRMTRMSPCH if FRMTRMSPCH else False
        self.FRMTTRIMINC = FRMTTRIMINC if FRMTTRIMINC else False
        self.SINGLELINE = SINGLELINE if SINGLELINE else False

    async def inference(self, prompt, tokens: int = 0):
        # Determine which endpoints to use
        def is_koboldcpp() -> bool:
            response = requests.get(f"{self.AI_PROVIDER_URI}/api/extra/version").json()[
                "result"
            ]
            if response == "KoboldCpp":
                return True
            return False

        koboldai_endpoint: Dict[str, str] = {
            "ctx_length": "/api/v1/config/max_context_length",
        }

        koboldcpp_endpoint: Dict[str, str] = {
            "ctx_length": "/api/extra/true_max_context_length",
        }

        def endpoint(data: str) -> str:
            if is_koboldcpp():
                return f"{self.AI_PROVIDER_URI}{koboldcpp_endpoint[data]}"
            return f"{self.AI_PROVIDER_URI}{koboldai_endpoint[data]}"

        # Common parameters to send to host
        prompt = f"{self.PROMPT_PREFIX}{prompt}{self.PROMPT_SUFFIX}"
        true_max_ctx_length = requests.get(endpoint("ctx_length")).json()["value"]

        def max_length() -> int:
            if self.MAX_LENGTH:
                return self.MAX_LENGTH
            if tokens < true_max_ctx_length:
                return true_max_ctx_length - tokens
            return 0

        params = {
            "prompt": prompt,
            "max_context_length": int(true_max_ctx_length),
            "max_length": int(max_length()),
            "rep_pen": float(self.REP_PEN),
            "rep_pen_range": int(self.REP_PEN_RANGE),
            "temperature": float(self.TEMPERATURE),
            "tfs": float(self.TFS),
            "top_a": float(self.TOP_A),
            "top_k": int(self.TOP_K),
            "top_p": float(self.TOP_P),
            "typical": float(self.TYPICAL),
        }

        # Optional parameters
        if self.MAX_CONTEXT_LENGTH:
            params["max_context_length"] = int(self.MAX_CONTEXT_LENGTH)

        if self.MAX_LENGTH:
            params["max_length"] = int(self.MAX_LENGTH)

        if self.QUIET:
            params["quiet"] = self.QUIET

        if self.SAMPLER_ORDER:

            def is_valid_sample_order(value: List[int]) -> bool:
                """Check if sample order is a list of integers ranging from 0 to (6 or 7)"""
                if not isinstance(value, list):
                    return False
                for num in value:
                    if not isinstance(num, int):
                        return False
                return set(value) == set(range(6)) or set(value) == set(range(7))

            if is_valid_sample_order(self.SAMPLER_ORDER):
                params["sampler_order"] = self.SAMPLER_ORDER

        if self.SAMPLER_SEED:
            params["sampler_seed"] = int(self.SAMPLER_SEED)

        if self.USE_DEFAULT_BADWORDSIDS:
            params["use_default_badwordsids"] = self.USE_DEFAULT_BADWORDSIDS

        if self.STOP_SEQUENCE:
            params["stop_sequence"] = self.STOP_SEQUENCE.split(",")
        else:
            self.STOP_SEQUENCE = []
            if self.PROMPT_PREFIX:
                self.STOP_SEQUENCE.append(self.PROMPT_PREFIX)
            if self.PROMPT_SUFFIX:
                self.STOP_SEQUENCE.append(self.PROMPT_SUFFIX)
            if self.STOP_SEQUENCE:
                params["stop_sequence"] = self.STOP_SEQUENCE

        # Specific API optional parameters
        if is_koboldcpp():
            params["min_p"] = float(self.MIN_P)

            if self.GRAMMAR:
                params["grammar"] = self.GRAMMAR
                params["grammar_retain_state"] = self.GRAMMAR_RETAIN_STATE

            if self.MIROSTAT > 0:
                params["mirostat"] = int(self.MIROSTAT)
                params["mirostat_tau"] = float(self.MIROSTAT_TAU)
                params["mirostat_eta"] = float(self.MIROSTAT_ETA)

        else:
            if not self.SAMPLER_FULL_DETERMINISM:
                params["sampler_full_determinism"] = self.SAMPLER_FULL_DETERMINISM

            if self.REP_PEN_SLOPE is not None:
                params["rep_pen_slope"] = self.REP_PEN_SLOPE

            if not self.DISABLE_INPUT_FORMATTING:
                params["disable_input_formatting"] = self.DISABLE_INPUT_FORMATTING
                if self.FRMTADSNSP:
                    params["frmtadsnsp"] = self.FRMTADSNSP

            if not self.DISABLE_OUTPUT_FORMATTING:
                params["disable_output_formatting"] = self.DISABLE_OUTPUT_FORMATTING
                if self.FRMTRMBLLN:
                    params["frmtrmblin"] = self.FRMTRMBLLN
                if self.FRMTRMSPCH:
                    params["frmtrmspch"] = self.FRMTRMSPCH
                if self.FRMTTRIMINC:
                    params["frmttriminc"] = self.FRMTTRIMINC

        # Fetch response
        response = requests.post(f"{self.AI_PROVIDER_URI}/api/v1/generate", json=params)
        json_response = response.json()

        try:
            text = json_response["results"][0]["text"].strip()

            if self.STOP_SEQUENCE:
                for sequence in self.STOP_SEQUENCE:
                    if text.endswith(sequence):
                        text = text[: -len(sequence)].rstrip()

            return text
        except:
            return json_response.json()["detail"][0]["msg"].strip()
