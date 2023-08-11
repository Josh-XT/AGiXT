try:
    from Bard import Chatbot
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "GoogleBard"])
    from Bard import Chatbot


class BardProvider:
    def __init__(self, BARD_TOKEN: str = "", **kwargs):
        self.requirements = ["GoogleBard"]
        self.AI_MODEL = "bard"
        self.BARD_TOKEN = BARD_TOKEN

    async def instruct(self, prompt, tokens: int = 0):
        try:
            bot = Chatbot(session_id=self.BARD_TOKEN)
            response = bot.ask(prompt)
            return response["content"].replace("\n", "\n")
        except Exception as e:
            return f"Bard Error: {e}"
