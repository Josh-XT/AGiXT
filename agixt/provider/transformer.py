import subprocess
import sys

try:
    from transformers import (
        AutoTokenizer,
        AutoModelForCausalLM,
        AutoModel,
        AutoModelForSeq2SeqLM,
        T5Tokenizer,
    )
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "transformers"])
    from transformers import (
        AutoTokenizer,
        AutoModelForCausalLM,
        AutoModel,
        AutoModelForSeq2SeqLM,
        T5Tokenizer,
    )


class TransformerProvider:
    def __init__(
        self,
        MODEL_PATH: str = "HuggingFaceH4/starchat-alpha",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4096,
        AI_MODEL: str = "starchat",
        **kwargs,
    ):
        self.requirements = ["transformers", "accelerate"]
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.MODEL_PATH = MODEL_PATH

    def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = int(self.MAX_TOKENS) - tokens
        try:
            model_path = self.MODEL_PATH
            if "chatglm" in model_path:
                tokenizer = AutoTokenizer.from_pretrained(
                    model_path, trust_remote_code=True
                )
                model = AutoModel.from_pretrained(model_path, trust_remote_code=True)
            elif "dolly" in model_path:
                tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True)
                model = AutoModelForCausalLM.from_pretrained(
                    model_path, low_cpu_mem_usage=True
                )
                # 50277 means "### End"
                tokenizer.eos_token_id = 50277
            elif "pythia" in model_path or "stablelm" in model_path:
                tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True)
                model = AutoModelForCausalLM.from_pretrained(
                    model_path, low_cpu_mem_usage=True
                )
            elif "t5" in model_path:
                tokenizer = T5Tokenizer.from_pretrained(model_path, use_fast=False)
                model = AutoModelForSeq2SeqLM.from_pretrained(
                    model_path, low_cpu_mem_usage=True
                )
            else:
                tokenizer = AutoTokenizer.from_pretrained(model_path)
                model = AutoModelForCausalLM.from_pretrained(
                    model_path, low_cpu_mem_usage=True
                )

            input_ids = tokenizer(prompt, return_tensors="pt").input_ids

            output_ids = model.generate(
                input_ids,
                pad_token_id=tokenizer.eos_token_id,
                temperature=self.AI_TEMPERATURE,
                max_new_tokens=max_new_tokens,
                no_repeat_ngram_size=2,
            )
            input_length = 1 if model.config.is_encoder_decoder else len(input_ids[0])
            output_ids = output_ids[0][input_length:]

            return tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        except Exception as e:
            return f"Transformer Error: {e}"
