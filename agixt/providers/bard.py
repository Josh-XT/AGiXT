try:
    from bardapi import Bard
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "bardapi"])
    from bardapi import Bard


class BardProvider:
    def __init__(self, BARD_TOKEN: str = "", **kwargs):
        self.requirements = ["bardapi"]
        self.AI_MODEL = "bard"
        self.BARD_TOKEN = BARD_TOKEN

    async def instruct(self, prompt, tokens: int = 0):
        try:
            response = Bard(token=self.BARD_TOKEN).get_answer(input_text=prompt)
            return response["content"].replace("\n", "\n")
        except Exception as e:
            return f"Bard Error: {e}"
