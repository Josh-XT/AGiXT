from revChatGPT.V1 import Chatbot


class ChatgptProvider:
    def __init__(
        self,
        CHATGPT_TOKEN: str = (None,),
        AI_MODEL: str = "gpt-3.5-turbo",
        **kwargs,
    ):
        self.requirements = ["revChatGPT"]
        self.bot = Chatbot(config={"access_token": CHATGPT_TOKEN})
        self.AI_MODEL = AI_MODEL

    def instruct(self, prompt, tokens: int = 0):
        try:
            response = ""
            for data in self.bot.ask(prompt):
                response = data["message"]
            return response
        except Exception as e:
            return f"revChatGPT Error: {e}"
