from Bard import Chatbot
from Config import Config

CFG = Config()


class AIProvider:
    def __init__(self):
        if CFG.AI_PROVIDER.lower() == "bard":
            self.chatbot = Chatbot(CFG.BARD_TOKEN)

    def instruct(self, prompt):
        response = self.chatbot.ask(prompt)
        return response["content"].replace("\n", "\n")
