from EdgeGPT import Chatbot, ConversationStyle


class BingProvider:
    def __init__(self, AI_TEMPERATURE: float = 0.7, **kwargs):
        self.requirements = ["EdgeGPT"]
        if AI_TEMPERATURE >= 0.7:
            self.style = ConversationStyle.creative
        if AI_TEMPERATURE <= 0.3 and AI_TEMPERATURE >= 0.0:
            self.style = ConversationStyle.precise
        if AI_TEMPERATURE >= 0.4 and AI_TEMPERATURE <= 0.6:
            self.style = ConversationStyle.balanced

    def instruct(self, prompt, tokens: int = 0):
        try:
            bot = Chatbot.create(cookie_path="./cookies.json")
            response = bot.ask(
                prompt,
                self.style,
                wss_link="wss://sydney.bing.com/sydney/ChatHub",
            )
            bot.close()
            return response
        except Exception as e:
            return f"EdgeGPT Error: {e}"
