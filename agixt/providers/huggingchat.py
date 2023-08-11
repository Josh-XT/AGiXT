import logging

try:
    from hugchat.hugchat import ChatBot
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "hugchat"])
    from hugchat.hugchat import ChatBot

MODELS = {"OpenAssistant/oasst-sft-6-llama-30b-xor", "meta-llama/Llama-2-70b-chat-hf"}

MODEL_MAX_LENGHT = 2048

DEFAULT_COOKIE_PATH = "./huggingchat-cookies.json"


class HuggingchatProvider:
    def __init__(
        self,
        MODEL_PATH: str = None,
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 1024,
        AI_MODEL: str = "openassistant",
        HUGGINGCHAT_COOKIE_PATH: str = DEFAULT_COOKIE_PATH,
        **kwargs,
    ):
        self.MODEL_PATH = MODEL_PATH
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.HUGGINGCHAT_COOKIE_PATH = HUGGINGCHAT_COOKIE_PATH

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
            self.session.switch_llm(MODELS.index(self.MODEL_PATH))

    async def instruct(self, prompt: str, tokens: int = 0) -> str:
        for result in self(
            prompt,
            temperature=self.AI_TEMPERATURE,
            max_new_tokens=min(MODEL_MAX_LENGHT - tokens, self.MAX_TOKENS),
        ):
            return result

    async def delete_conversation(self):
        self.session.delete_conversation(self.session.current_conversation)
        self.session.current_conversation = ""


if __name__ == "__main__":
    import json, os
    from getpass import getpass
    from hugchat.login import Login

    print("Login for HuggingChat")
    cookie_path = os.getenv("HUGGINGCHAT_COOKIE_PATH", DEFAULT_COOKIE_PATH)
    email = input("Email: ")
    if email:
        signin = Login(email, getpass())
        cookies = signin.login().get_dict()
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(cookies))

    import asyncio

    async def run_test():
        response = await HuggingchatProvider(
            HUGGINGCHAT_COOKIE_PATH=cookie_path
        ).instruct("Hello")
        print(f"Test: {response}")

    asyncio.run(run_test())
