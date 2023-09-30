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
        AI_MODEL: str = "default",
        PROMPT_PREFIX: str = "",
        PROMPT_SUFFIX: str = "",
        STOP_SEQUENCE: str = "</s>",
        MAX_TOKENS: int = 2048,
        AI_TEMPERATURE: float = 0.8,
        AI_TOP_P: float = 0.95,
        AI_TOP_K: int = 40,
        REPEAT_PENALTY: float = 1.1,
        FREQUENCY_PENALTY: float = 0.0,
        PRESENCE_PENALTY: float = 0.0,
        TFS_Z: float = 1.0,
        MIROSTAT_MODE: int = 0,
        MIROSTAT_ETA: float = 0.1,
        MIROSTAT_TAU: float = 5.0,
        LOGITS_PROCESSOR=None,
        GRAMMAR=None,
        GPU_LAYERS: int = 0,
        BATCH_SIZE: int = 2048,
        THREADS: int = 0,
        THREADS_BATCH: int = 0,
        MAIN_GPU: int = 0,
        TENSOR_SPLIT: int = 0,
        ROPE_FREQ_BASE: float = 0.0,
        ROPE_FREQ_SCALE: float = 0.0,
        LAST_N_TOKENS_SIZE: int = 64,
        USE_LOW_VRAM: bool = False,
        USE_MUL_MAT_Q: bool = True,
        USE_F16_KV: bool = True,
        USE_LOGITS_ALL: bool = False,
        USE_VOCAB_ONLY: bool = False,
        USE_MMAP: bool = True,
        USE_MLOCK: bool = False,
        USE_EMBEDDING: bool = False,
        USE_NUMA: bool = False,
        LORA_BASE: str = "",
        LORA_PATH: str = "",
        LORA_SCALE: float = 1.0,
        **kwargs,
    ):
        self.requirements = ["llama-cpp-python"]
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.8
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.95
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 2048
        self.AI_MODEL = AI_MODEL if AI_MODEL else "default"
        self.GPU_LAYERS = GPU_LAYERS if GPU_LAYERS else 0
        self.BATCH_SIZE = BATCH_SIZE if BATCH_SIZE else 2048
        self.THREADS = THREADS if THREADS else None
        self.THREADS_BATCH = THREADS_BATCH if THREADS_BATCH else None
        self.STOP_SEQUENCE = STOP_SEQUENCE if STOP_SEQUENCE else "</s>"
        self.LORA_BASE = LORA_BASE if LORA_BASE else ""
        self.LORA_PATH = LORA_PATH if LORA_PATH else ""
        self.LORA_SCALE = LORA_SCALE if LORA_SCALE else 1.0
        self.MAIN_GPU = MAIN_GPU if MAIN_GPU else 0
        self.TENSOR_SPLIT = TENSOR_SPLIT if TENSOR_SPLIT else 0
        self.ROPE_FREQ_BASE = ROPE_FREQ_BASE
        self.ROPE_FREQ_SCALE = ROPE_FREQ_SCALE
        self.LAST_N_TOKENS_SIZE = LAST_N_TOKENS_SIZE if LAST_N_TOKENS_SIZE else 64
        self.USE_LOW_VRAM = USE_LOW_VRAM if USE_LOW_VRAM else False
        self.USE_MUL_MAT_Q = USE_MUL_MAT_Q if USE_MUL_MAT_Q else True
        self.USE_F16_KV = USE_F16_KV if USE_F16_KV else True
        self.USE_LOGITS_ALL = USE_LOGITS_ALL if USE_LOGITS_ALL else False
        self.USE_VOCAB_ONLY = USE_VOCAB_ONLY if USE_VOCAB_ONLY else False
        self.USE_MMAP = USE_MMAP if USE_MMAP else True
        self.USE_MLOCK = USE_MLOCK if USE_MLOCK else False
        self.USE_EMBEDDING = USE_EMBEDDING if USE_EMBEDDING else False
        self.USE_NUMA = USE_NUMA if USE_NUMA else False
        self.PROMPT_PREFIX = PROMPT_PREFIX if PROMPT_PREFIX else ""
        self.PROMPT_SUFFIX = PROMPT_SUFFIX if PROMPT_SUFFIX else ""
        self.AI_TOP_K = AI_TOP_K if AI_TOP_K else 40
        self.REPEAT_PENALTY = REPEAT_PENALTY if REPEAT_PENALTY else 1.1
        self.FREQUENCY_PENALTY = FREQUENCY_PENALTY if FREQUENCY_PENALTY else 0.0
        self.PRESENCE_PENALTY = PRESENCE_PENALTY if PRESENCE_PENALTY else 0.0
        self.TFS_Z = TFS_Z if TFS_Z else 1.0
        self.MIROSTAT_MODE = MIROSTAT_MODE if MIROSTAT_MODE else 0
        self.MIROSTAT_ETA = MIROSTAT_ETA if MIROSTAT_ETA else 0.1
        self.MIROSTAT_TAU = MIROSTAT_TAU if MIROSTAT_TAU else 5.0
        self.LOGITS_PROCESSOR = LOGITS_PROCESSOR if LOGITS_PROCESSOR else None
        self.GRAMMAR = GRAMMAR if GRAMMAR else None
        self.MODEL_PATH = MODEL_PATH
        if self.MODEL_PATH:
            try:
                self.MAX_TOKENS = int(self.MAX_TOKENS)
            except:
                self.MAX_TOKENS = 2048

    async def instruct(self, prompt, tokens: int = 0):
        prompt = self.PROMPT_PREFIX + prompt + self.PROMPT_SUFFIX
        if os.path.isfile(self.MODEL_PATH):
            self.model = Llama(
                model_path=self.MODEL_PATH,
                n_gpu_layers=int(self.GPU_LAYERS) if self.GPU_LAYERS else 0,
                n_threads=int(self.THREADS) if self.THREADS else None,
                n_threads_batch=int(self.THREADS_BATCH) if self.THREADS_BATCH else None,
                n_batch=int(self.BATCH_SIZE) if self.BATCH_SIZE else 512,
                n_ctx=int(self.MAX_TOKENS),
                seed=-1,
                main_gpu=int(self.MAIN_GPU) if self.MAIN_GPU else None,
                tensor_split=int(self.TENSOR_SPLIT) if self.TENSOR_SPLIT else None,
                rope_freq_base=float(self.ROPE_FREQ_BASE)
                if self.ROPE_FREQ_BASE
                else None,
                rope_freq_scale=float(self.ROPE_FREQ_SCALE)
                if self.ROPE_FREQ_SCALE
                else None,
                last_n_tokens_size=int(self.LAST_N_TOKENS_SIZE)
                if self.LAST_N_TOKENS_SIZE
                else 64,
                low_vram=bool(self.USE_LOW_VRAM) if self.USE_LOW_VRAM else None,
                mul_mat_q=bool(self.USE_MUL_MAT_Q) if self.USE_MUL_MAT_Q else None,
                f16_kv=bool(self.USE_F16_KV) if self.USE_F16_KV else None,
                logits_all=bool(self.USE_LOGITS_ALL) if self.USE_LOGITS_ALL else None,
                vocab_only=bool(self.USE_VOCAB_ONLY) if self.USE_VOCAB_ONLY else None,
                use_mmap=bool(self.USE_MMAP) if self.USE_MMAP else None,
                use_mlock=bool(self.USE_MLOCK) if self.USE_MLOCK else None,
                embedding=bool(self.USE_EMBEDDING) if self.USE_EMBEDDING else False,
                numa=bool(self.USE_NUMA) if self.USE_NUMA else None,
                lora_base=self.LORA_BASE if self.LORA_BASE else None,
                lora_path=self.LORA_PATH if self.LORA_PATH else None,
                lora_scale=float(self.LORA_SCALE) if self.LORA_SCALE else None,
            )
        else:
            logging.info("Unable to find model path.")
            return None
        response = self.model(
            prompt=prompt,
            stop=[self.STOP_SEQUENCE],
            temperature=float(self.AI_TEMPERATURE),
            top_p=self.AI_TOP_P,
            top_k=self.AI_TOP_K,
            repeat_penalty=float(self.REPEAT_PENALTY) if self.REPEAT_PENALTY else None,
            frequency_penalty=float(self.FREQUENCY_PENALTY)
            if self.FREQUENCY_PENALTY
            else None,
            presence_penalty=float(self.PRESENCE_PENALTY)
            if self.PRESENCE_PENALTY
            else None,
            tfs_z=float(self.TFS_Z) if self.TFS_Z else None,
            mirostat_mode=int(self.MIROSTAT_MODE) if self.MIROSTAT_MODE else None,
            mirostat_eta=float(self.MIROSTAT_ETA) if self.MIROSTAT_ETA else None,
            mirostat_tau=float(self.MIROSTAT_TAU) if self.MIROSTAT_TAU else None,
            logits_processor=self.LOGITS_PROCESSOR if self.LOGITS_PROCESSOR else None,
            grammar=self.GRAMMAR if self.GRAMMAR else None,
        )
        data = response["choices"][0]["text"]
        data = data.replace(prompt, "")
        data = data.lstrip("\n")
        try:
            self.model.reset()
        except:
            print("Unable to reset model.")
        return data
