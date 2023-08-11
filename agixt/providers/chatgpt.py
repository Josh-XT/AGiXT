try:
    from revChatGPT.V1 import Chatbot
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "revChatGPT"])
    from revChatGPT.V1 import Chatbot


# python -m pip install --upgrade revChatGPT
# Get access token from https://chat.openai.com/api/auth/session
class ChatgptProvider:
    def __init__(
        self,
        CHATGPT_TOKEN: str = "",
        AI_MODEL: str = "gpt-3.5-turbo",
        **kwargs,
    ):
        self.requirements = ["revChatGPT"]
        try:
            self.bot = Chatbot(
                config={"access_token": CHATGPT_TOKEN, "model": AI_MODEL}
            )
        except:
            raise Exception(
                "Invalid Chatgpt Token. Get access token from https://chat.openai.com/api/auth/session"
            )
        self.AI_MODEL = AI_MODEL

    async def instruct(self, prompt, tokens: int = 0):
        response = ""
        try:
            for data in self.bot.ask(prompt=prompt, model=self.AI_MODEL):
                response = data["message"]
            return response
        except Exception as e:
            return f"Chatgpt Error: {e}"
