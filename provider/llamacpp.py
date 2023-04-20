import subprocess
from Config import Config
from llama_cpp import Llama

CFG = Config()

class AIProvider:
    def __init__(self):
        if CFG.MODEL_PATH:
            self.llamacpp = Llama(model_path=CFG.MODEL_PATH)

    def instruct(self, prompt):
        output = self.llamacpp(f"Q: {prompt}", max_tokens=CFG.MAX_TOKENS, stop=["Q:", "\n"], echo=True)
        return output["choices"][0]["text"]