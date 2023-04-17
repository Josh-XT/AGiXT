import subprocess

class AIProvider:
    def __init__(self, temperature, max_tokens):
        self.temperature = temperature
        self.max_tokens = max_tokens

    def instruct(self, prompt):
        cmd = [f"llama/main", "-p", prompt]
        result = subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True)
        return result.stdout.strip()
