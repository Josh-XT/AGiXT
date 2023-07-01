import logging
import time

import g4f
from g4f.Provider import (
    Ails,
    You,
    Bing,
    Yqcloud,
    Theb,
    Aichat,
    Bard,
    Vercel,
    Forefront,
    Lockchat,
    Liaobots,
    H2o,
    ChatgptLogin,
    DeepAi,
    GetGpt,
)


class Gpt4freeProvider:
    def __init__(
        self,
        AI_MODEL: str = "gpt-3.5-turbo",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4000,
        **kwargs,
    ):
        self.requirements = ["gpt4free"]
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.FAILED_PROVIDERS = []
        self.providers = [  # Exclude providers that require auth
            Yqcloud,
            Aichat,
            Lockchat,
            ChatgptLogin,
            DeepAi,
            GetGpt,
            Ails,
            You,
            Bing,
            Theb,
            Vercel,
            H2o,
        ]

    async def provider_failure(self, provider):
        if provider not in self.FAILED_PROVIDERS:
            self.FAILED_PROVIDERS.append(provider)
            logging.info(f"[GPT4Free] Failed provider: {provider}")
            if len(self.FAILED_PROVIDERS) == len(self.providers):
                self.FAILED_PROVIDERS = []
                logging.info(
                    "All providers failed, sleeping for 10 seconds before trying again..."
                )
                time.sleep(10)

    async def instruct(self, prompt, tokens: int = 0):
        for provider in self.providers:
            try:
                if provider not in self.FAILED_PROVIDERS:
                    response = g4f.ChatCompletion.create(
                        model=g4f.Model.gpt_35_turbo,
                        provider=provider,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    if response:
                        if provider == Ails:
                            if "error" in response and "message" in response:
                                response = None
                        elif provider == Vercel:
                            if response == "Vercel is currently not working.":
                                response = None
                        if (
                            response
                            == "Unable to fetch the response, Please try again."
                        ):
                            response = None
                    if response and len(response) > 1:
                        return response
                    else:
                        await self.provider_failure(provider)

            except Exception as e:
                logging.error(f"[GPT4Free] Exception: {e}")
                await self.provider_failure(provider)
