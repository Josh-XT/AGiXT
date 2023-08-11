from pipeline import PipelineProvider
from transformers import AutoTokenizer

try:
    from petals import AutoDistributedModelForCausalLM
except ImportError:
    import subprocess, sys

    subprocess.check_call([sys.executable, "-m", "pip", "install", "petals"])
    from petals import AutoDistributedModelForCausalLM


class PetalPipeline:
    def __init__(self, model: str, **kwargs):
        self.tokenizer = AutoTokenizer.from_pretrained(model)
        self.model = AutoDistributedModelForCausalLM.from_pretrained(model, **kwargs)

    def __call__(self, prompt: str, **kwargs):
        input_ids = self.tokenizer(prompt, return_tensors="pt")["input_ids"]
        outputs = self.model.generate(input_ids, **kwargs)[0]
        return self.tokenizer.decode(outputs, skip_special_tokens=True)[len(prompt) :]


class PetalProvider(PipelineProvider):
    def __init__(
        self,
        MODEL_PATH: str = "stabilityai/StableBeluga2",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 1024,
        AI_MODEL: str = "",
        HUGGINGFACE_API_KEY: str = None,
        **kwargs,
    ):
        super().__init__(
            MODEL_PATH,
            AI_TEMPERATURE,
            MAX_TOKENS,
            AI_MODEL,
            HUGGINGFACE_API_KEY,
            **kwargs,
        )

    async def instruct(self, prompt, tokens: int = 0):
        self.load_pipeline()
        return self.pipeline(
            prompt,
            temperature=self.AI_TEMPERATURE,
            max_new_tokens=self.get_max_new_tokens(tokens),
        )

    def load_pipeline(self):
        if not self.pipeline:
            self.load_args()
            self.pipeline = PetalPipeline(self.MODEL_PATH, **self.pipeline_kwargs)


if __name__ == "__main__":
    import asyncio

    async def run_test():
        prompt = f"### System:\n\n\n### User:\nHello\n\n### Assistant:\n"
        response = await PetalProvider(resume_download=True).instruct(prompt)
        print(f"Test: {response}")

    asyncio.run(run_test())
