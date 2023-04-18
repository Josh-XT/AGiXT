import subprocess
from Config import Config

CFG = Config()

class AIProvider:
    def instruct(self, prompt):
        llama_path = CFG.LLAMACPP_PATH if CFG.LLAMACPP_PATH else "llama/main"
        cmd = [llama_path, "-p", prompt]
        result = subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True)
        return result.stdout.strip()