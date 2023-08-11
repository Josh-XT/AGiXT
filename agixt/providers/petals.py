try:
    from transformers import AutoTokenizer
except:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "transformers"])
    from transformers import AutoTokenizer
try:
    from petals import AutoDistributedModelForCausalLM
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "petals"])
    from petals import AutoDistributedModelForCausalLM


class PetalsProvider:
    def __init__(
        self,
        MAX_TOKENS: int = 4096,
        AI_MODEL="stabilityai/StableBeluga2",
        AI_TEMPERATURE: float = 0.9,
        AI_TOP_P: float = 0.6,
        **kwargs,
    ):
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 4096
        self.AI_MODEL = AI_MODEL if AI_MODEL else "stabilityai/StableBeluga2"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.9
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.6
        self.tokenizer = AutoTokenizer.from_pretrained(self.AI_MODEL)
        self.model = AutoDistributedModelForCausalLM.from_pretrained(self.AI_MODEL)

    async def instruct(self, prompt, tokens: int = 0):
        try:
            max_new_tokens = int(self.MAX_TOKENS) - int(tokens)
            inputs = self.tokenizer(prompt, return_tensors="pt")["input_ids"]
            outputs = self.model.generate(
                inputs,
                max_new_tokens=max_new_tokens,
                temperature=float(self.AI_TEMPERATURE),
                top_p=float(self.AI_TOP_P),
            )
            return self.tokenizer.decode(outputs[0])
        except Exception as e:
            return f"Petals Error: {e}"
