from Config import Config
from llama_cpp import Llama

CFG = Config()

class AIProvider:
    def __init__(self):
        if CFG.MODEL_PATH:
            try:
                self.max_tokens = int(CFG.MAX_TOKENS)
            except:
                self.max_tokens = 2000
            self.llamacpp = Llama(model_path=CFG.MODEL_PATH, n_ctx=self.max_tokens)

    def instruct(self, prompt):
        output = self.llamacpp(f"Q: {prompt}", max_tokens=self.max_tokens, stop=["Q:", "\n"], echo=True)
        return output["choices"][0]["text"]