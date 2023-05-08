from Bard import Chatbot
from Config import Config

CFG = Config()


class BardProvider:
    def __init__(self, BARD_TOKEN: str = "", AI_MODEL: str = "bard", **kwargs):
        self.requirements = ["GoogleBard"]
        self.BARD_TOKEN = BARD_TOKEN
        self.AI_MODEL = AI_MODEL

    def instruct(self, prompt, tokens: int = 0):
        try:
            chatbot = Chatbot(self.BARD_TOKEN)
            response = chatbot.ask(prompt)
            return response["content"].replace("\n", "\n")
        except Exception as e:
            return f"Bard Error: {e}"
