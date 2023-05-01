from Bard import Chatbot
from Config import Config

CFG = Config()


class BardProvider:
    def __init__(self, BARD_TOKEN: str = "", **kwargs):
        self.requirements = ["GoogleBard"]
        if CFG.AI_PROVIDER.lower() == "bard":
            self.chatbot = Chatbot(BARD_TOKEN)

    def instruct(self, prompt):
        response = self.chatbot.ask(prompt)
        return response["content"].replace("\n", "\n")
