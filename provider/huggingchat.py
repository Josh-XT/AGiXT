from hugchat import hugchat


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
            max_new_tokens = int(self.MAX_TOKENS) - tokens - 428
            id = chatbot.new_conversation()
            response = chatbot.chat(
                text=prompt,
                temperature=self.AI_TEMPERATURE,
                max_new_tokens=max_new_tokens,
                stream=False,
            )
            return response
        except Exception as e:
            print(e)
            return f"HuggingChat Provider Failure: {e}."
