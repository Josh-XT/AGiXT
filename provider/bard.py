from Bard import Chatbot


class BardProvider:
    def __init__(self, BARD_TOKEN: str = "", **kwargs):
        self.requirements = ["GoogleBard"]
        self.AI_MODEL = "bard"
        self.BARD_TOKEN = BARD_TOKEN

    def instruct(self, prompt, tokens: int = 0):
        try:
            bot = Chatbot(self.BARD_TOKEN)
            response = bot.ask(prompt)
            return response["content"].replace("\n", "\n")
        except Exception as e:
            return f"Bard Error: {e}"
