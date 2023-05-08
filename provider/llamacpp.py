try:
    from pyllamacpp.model import Model
except:
    print("Failed to import pyllamacpp.")


class LlamacppProvider:
    def __init__(
        self,
        MODEL_PATH: str = "",
        MAX_TOKENS: int = 2000,
        AI_TEMPERATURE: float = 0.7,
        AI_MODEL: str = "default",
        **kwargs
    ):
        self.requirements = ["pyllamacpp"]
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        if MODEL_PATH:
            try:
                self.MAX_TOKENS = int(self.MAX_TOKENS)
            except:
                self.MAX_TOKENS = 2000
            self.model = Model(ggml_model=MODEL_PATH, n_ctx=self.MAX_TOKENS)

    def instruct(self, prompt, tokens: int = 0):
        return self.model.generate(
            prompt, n_predict=55, n_threads=8, temp=float(self.AI_TEMPERATURE)
        )
