import logging

try:
    from hugchat.hugchat import ChatBot
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "hugchat"])
    from hugchat.hugchat import ChatBot


class HuggingchatProvider:
    def __init__(
        self,
        HUGGINGCHAT_COOKIE_PATH: str = "./huggingchat-cookies.json",
        MODEL_PATH: str = None,
        AI_MODEL: str = "meta-llama/Llama-2-70b-chat-hf",
        MAX_TOKENS: int = 2048,
        AI_TEMPERATURE: float = 0.7,
        **kwargs,
    ):
        self.MODEL_PATH = MODEL_PATH
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.HUGGINGCHAT_COOKIE_PATH = HUGGINGCHAT_COOKIE_PATH
        self.MODELS = {
            "OpenAssistant/oasst-sft-6-llama-30b-xor",
            "meta-llama/Llama-2-70b-chat-hf",
        }

    def __call__(self, prompt: str, **kwargs) -> str:
        try:
            self.load_session()
            yield self.session.chat(text=prompt, **kwargs)
            self.delete_conversation()
        except Exception as e:
            logging.info(e)

    def load_session(self):
        self.session = ChatBot(cookie_path=self.HUGGINGCHAT_COOKIE_PATH)
        if self.MODEL_PATH:
            self.session.switch_llm(self.MODELS.index(self.MODEL_PATH))

    async def instruct(self, prompt: str, tokens: int = 0) -> str:
        for result in self(
            prompt,
            temperature=self.AI_TEMPERATURE,
            max_new_tokens=min(2048 - tokens, self.MAX_TOKENS),
        ):
            return result

    async def delete_conversation(self):
        self.session.delete_conversation(self.session.current_conversation)
        self.session.current_conversation = ""
