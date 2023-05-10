from EdgeGPT import Chatbot, ConversationStyle
import asyncio
import nest_asyncio


class BingProvider:
    def __init__(self, AI_TEMPERATURE: float = 0.7, **kwargs):
        nest_asyncio.apply()
        self.requirements = ["EdgeGPT"]
        if AI_TEMPERATURE >= 0.7:
            self.style = ConversationStyle.creative
        if AI_TEMPERATURE <= 0.3 and AI_TEMPERATURE >= 0.0:
            self.style = ConversationStyle.precise
        if AI_TEMPERATURE >= 0.4 and AI_TEMPERATURE <= 0.6:
            self.style = ConversationStyle.balanced

    async def ask(self, prompt, tokens: int = 0):
        try:
            bot = await Chatbot.create(cookie_path="./cookies.json")
            response = await bot.ask(
                prompt=prompt,
                conversation_style=self.style,
            )
            await bot.close()
            return response
        except Exception as e:
            return f"EdgeGPT Error: {e}"

    def instruct(self, prompt, tokens: int = 0):
        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(self.ask(prompt, tokens))
        return response
