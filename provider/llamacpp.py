from Config import Config

try:
    from pyllamacpp.model import Model
except:
    print("Failed to import pyllamacpp.")
CFG = Config()


class AIProvider:
    def __init__(self):
        if CFG.MODEL_PATH:
            try:
                self.max_tokens = int(CFG.MAX_TOKENS)
            except:
                self.max_tokens = 2000
            self.model = Model(ggml_model=CFG.MODEL_PATH, n_ctx=self.max_tokens)
            # TODO: Need to reseach to add temperature, no obvious flag.

    def instruct(self, prompt):
        return self.model.generate(prompt, n_predict=55, n_threads=8)
