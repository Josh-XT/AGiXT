from Bard import Chatbot
from Config import Config

CFG = Config()


class BardProvider:
    def __init__(self, BARD_TOKEN: str = "", **kwargs):
        self.requirements = ["GoogleBard"]
        self.chatbot = Chatbot(BARD_TOKEN)

    def instruct(self, prompt):
        response = self.chatbot.ask(prompt)
        return response["content"].replace("\n", "\n")
