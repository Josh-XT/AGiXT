try:
    import poe
except ImportError:
    import subprocess
    import sys

    subprocess.check_call([sys.executable, "-m", "pip", "install", "poe-api"])
    import poe

"""
Models for Poe:

self.client.bot_names = {
  "capybara": "Sage",
  "a2": "Claude-instant",
  "nutria": "Dragonfly",
  "a2_100k": "Claude-instant-100k",
  "beaver": "GPT-4",
  "chinchilla": "ChatGPT",
  "a2_2": "Claude+"
}
Notes for Free accounts:

Claude+ (a2_2) has a limit of 3 messages per day. 
GPT-4 (beaver) has a limit of 1 message per day. 
Claude-instant-100k (c2_100k) is completely inaccessible for free accounts. 
For all the other chatbots, there seems to be a rate limit of 10 messages per minute.
"""


class PoeProvider:
    def __init__(self, POE_TOKEN: str = "", AI_MODEL: str = "chinchilla", **kwargs):
        self.requirements = ["poe-api"]
        self.POE_TOKEN = POE_TOKEN
        self.AI_MODEL = AI_MODEL.lower()

    async def instruct(self, prompt, tokens: int = 0):
        try:
            client = poe.Client(token=self.POE_TOKEN)
            if self.AI_MODEL not in client.bot_names:
                try:
                    self.AI_MODEL = client.get_bot_by_codename(self.AI_MODEL)
                except:
                    raise Exception(f"Invalid AI Model: {self.AI_MODEL}")
            for chunk in client.send_message(chatbot=self.AI_MODEL, message=prompt):
                pass
            response = chunk["text"].replace("\n", "\n")
            return response
        except Exception as e:
            return f"Poe Error: {e}"
