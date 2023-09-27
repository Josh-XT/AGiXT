from transformers import pipeline

has_accelerate = True
try:
    import torch
    import accelerate
except ImportError:
    has_accelerate = False

has_bitsandbytes = True
try:
    import bitsandbytes
except ImportError:
    has_bitsandbytes = False


def is_cuda_available():
    if not torch.cuda.is_available():
        return False
    return has_accelerate


class PipelineProvider:
    def __init__(
        self,
        HUGGINGFACE_API_KEY: str = None,
        MODEL_PATH: str = "HuggingFaceH4/starchat-beta",
        AI_MODEL: str = "starchat",
        MAX_TOKENS: int = 1024,
        AI_TEMPERATURE: float = 0.7,
        **kwargs,
    ):
        self.requirements = ["petals", "transformers[accelerate]", "torch"]
        self.MODEL_PATH = MODEL_PATH
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.pipeline = None
        self.pipeline_kwargs = kwargs
        if HUGGINGFACE_API_KEY:
            self.pipeline_kwargs["use_auth_token"] = HUGGINGFACE_API_KEY

    async def instruct(self, prompt, tokens: int = 0):
        self.load_pipeline()
        return self.pipeline(
            prompt,
            temperature=self.AI_TEMPERATURE,
            return_full_text=False,
            max_new_tokens=self.get_max_new_tokens(tokens),
        )[0]["generated_text"]

    def load_args(self):
        if is_cuda_available():
            # Use "half" = bfloat16 or float16
            if "torch_dtype" not in self.pipeline_kwargs:
                self.pipeline_kwargs["torch_dtype"] = (
                    torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
                )
            # Enable GPU support
            if (
                "device_map" not in self.pipeline_kwargs
                and "device" not in self.pipeline_kwargs
            ):
                self.pipeline_kwargs["device_map"] = "auto"
                # Use "quantization"
                if has_bitsandbytes:
                    self.pipeline_kwargs["load_in_8bit"] = True

    def load_pipeline(self):
        if not self.pipeline:
            self.load_args()
            self.pipeline = pipeline(
                "text-generation", self.MODEL_PATH, **self.pipeline_kwargs
            )

    def get_max_length(self):
        self.load_pipeline()
        if self.pipeline.model.generation_config.max_length:
            return self.pipeline.model.generation_config.max_length
        max_length = self.pipeline.tokenizer.model_max_length
        if max_length == int(1e30):
            return 4096
        return max_length

    def get_max_new_tokens(self, input_length: int = 0) -> int:
        max_length = self.get_max_length() - input_length
        if max_length > 0 and self.MAX_TOKENS > max_length:
            return max_length
        return self.MAX_TOKENS
