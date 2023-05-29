from hugchat import hugchat
import logging


class HuggingchatProvider:
    def __init__(
        self,
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 2000,
        AI_MODEL: str = "openassistant",
        HUGGINGCHAT_COOKIE_PATH: str = "./huggingchat-cookies.json",
        **kwargs,
    ):
        self.requirements = []
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = int(MAX_TOKENS)
        self.AI_MODEL = AI_MODEL
        self.HUGGINGCHAT_COOKIE_PATH = HUGGINGCHAT_COOKIE_PATH

    def instruct(self, prompt: str, tokens: int = 0) -> str:
        try:
            chatbot = hugchat.ChatBot(cookie_path=self.HUGGINGCHAT_COOKIE_PATH)
            id = chatbot.new_conversation()
            response = chatbot.chat(
                text=prompt,
                temperature=float(self.AI_TEMPERATURE),
            )
            return response
        except Exception as e:
            logging.info(e)
            return f"HuggingChat Provider Failure: {e}."
