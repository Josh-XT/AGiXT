from EdgeGPT import Chatbot, ConversationStyle
import asyncio
import os
import json


class BingProvider:
    def __init__(self, AI_TEMPERATURE: float = 0.7, **kwargs):
        self.AI_MODEL = "bing"
        self.requirements = ["EdgeGPT"]
        self.AI_TEMPERATURE = AI_TEMPERATURE

    async def ask(self, prompt, tokens: int = 0):
        cookie_path = "./cookies.json"
        # Check if cookies exist
        if os.path.exists(cookie_path):
            with open(cookie_path, "r") as f:
                cookies = f.read()
            cookies = json.loads(cookies)
        try:
            bot = await Chatbot.create(cookies=cookies)
            response = await bot.ask(
                prompt=prompt,
                conversation_style=ConversationStyle.creative,
            )
            await bot.close()
            return response
        except Exception as e:
            return f"EdgeGPT Error: {e}"

    def instruct(self, prompt, tokens: int = 0):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _ask_and_set_result():
            result = await self.ask(prompt, tokens)
            return result

        response = loop.run_until_complete(_ask_and_set_result())

        # Closing the loop after use
        loop.close()

        # Extract the text of the bot's message
        bot_response = ""
        for message in response.get("item", {}).get("messages", []):
            if message.get("author") == "bot":
                bot_response = message.get("text") or message.get("hiddenText")

                # If the response is in an Adaptive Card
                if "adaptiveCards" in message:
                    for card in message["adaptiveCards"]:
                        for item in card.get("body", []):
                            if item["type"] == "TextBlock":
                                bot_response = item.get("text")

                # Stop at the first bot message we find
                if bot_response:
                    break

        return bot_response
