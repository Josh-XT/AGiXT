from EdgeGPT import Chatbot, ConversationStyle


class BingProvider:
    def __init__(self, **kwargs):
        self.requirements = ["EdgeGPT"]

    def instruct(self, prompt, tokens: int = 0):
        try:
            bot = Chatbot.create(cookie_path="./cookies.json")
            response = bot.ask(
                prompt,
                ConversationStyle.creative,
                wss_link="wss://sydney.bing.com/sydney/ChatHub",
            )
            bot.close()
            return response
        except Exception as e:
            return f"EdgeGPT Error: {e}"
