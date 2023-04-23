from Config import Config

from pyllamacpp.model import Model
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

    def new_text_callback(self, text: str):
        print(text, end="", flush=True)

    def instruct(self, prompt):
        output = self.model.generate(f"Q: {prompt}", n_predict=55, new_text_callback=self.new_text_callback, n_threads=8)
        return output