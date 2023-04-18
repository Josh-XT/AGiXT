import subprocess

class AIProvider:
    def instruct(self, prompt):
        cmd = ["llama/main", "-p", prompt]
        result = subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True)
        return result.stdout.strip()
