from local_llm import LLM
import logging
import os


class LocalProvider:
    def __init__(
        self,
        AI_MODEL: str = "Mistral-7B-OpenOrca",
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.95,
        PROMPT_PREFIX: str = "",
        PROMPT_SUFFIX: str = "",
        **kwargs,
    ):
        self.requirements = ["local-llm"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "Mistral-7B-OpenOrca"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.95
        self.PROMPT_PREFIX = PROMPT_PREFIX if PROMPT_PREFIX else ""
        self.PROMPT_SUFFIX = PROMPT_SUFFIX if PROMPT_SUFFIX else ""

    def models(self):
        return LLM().models()

    async def inference(self, prompt, tokens: int = 0):
        models_dir = os.path.join(os.getcwd(), "models")
        prompt = f"{self.PROMPT_PREFIX}{prompt}{self.PROMPT_SUFFIX}"
        if self.PROMPT_PREFIX != "" and self.PROMPT_SUFFIX != "":
            format_prompt = False
        else:
            format_prompt = True
        try:
            response = LLM(
                models_dir=models_dir,
                model=self.AI_MODEL,
                temperature=float(self.AI_TEMPERATURE),
                top_p=float(self.AI_TOP_P),
            ).completion(prompt=prompt, format_prompt=format_prompt)
            return response["choices"][0]["text"]
        except Exception as e:
            logging.error(f"Local-LLM Error: {e}")
            return "Unable to communicate with Local-LLM."
