import logging
import time

from g4f import Provider, ChatCompletion
from g4f.models import ModelUtils

providers = [
    # Working:
    Provider.GetGpt,
    # Works sometimes:
    Provider.Aichat,
    Provider.Ails,
    Provider.Vercel,
    Provider.Yqcloud,
    Provider.Acytoo,
    Provider.Equing,
    Provider.Opchatgpts,
    Provider.Wewordle,
    Provider.DeepAi,  # Wierd response seem complete the prompt only
    Provider.ChatgptLogin,  # seem to works but long
    Provider.EasyChat,
    Provider.You,
    # Not working today:
    Provider.AiService,
    Provider.AItianhu,
    Provider.Bing,
    # Provider.DfeHub, endless loop
    Provider.Lockchat,
    Provider.Theb,
    Provider.FastGpt,
    Provider.Forefront,
    Provider.ChatgptAi,
    Provider.H2o,
]


def validate_response(response):
    if not response:
        raise RuntimeError("Empty response")
    elif not isinstance(response, str):
        raise RuntimeError("Response is not a string")
    elif response in (
        "Vercel is currently not working.",
        "Unable to fetch the response, Please try again.",
    ) or response.startswith('{"error":{"message":'):
        raise RuntimeError(f"Response: {response}")
    else:
        return response


class Gpt4freeProvider:
    def __init__(
        self,
        AI_MODEL: str = "gpt-3.5-turbo",
        MAX_TOKENS: int = 4096,
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        WAIT_BETWEEN_REQUESTS: int = 1,
        WAIT_AFTER_FAILURE: int = 3,
        **kwargs,
    ):
        self.requirements = ["g4f", "httpx"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-3.5-turbo"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 4096
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.WAIT_BETWEEN_REQUESTS = (
            WAIT_BETWEEN_REQUESTS if WAIT_BETWEEN_REQUESTS else 1
        )
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE if WAIT_AFTER_FAILURE else 3

    async def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = (
            int(self.MAX_TOKENS) - int(tokens) if tokens > 0 else self.MAX_TOKENS
        )
        for provider in providers:
            if not provider.working:
                continue
            if int(self.WAIT_BETWEEN_REQUESTS) > 0:
                time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
            try:
                logging.info(f"[Gpt4Free] Use provider: {provider.__name__}")
                response = ChatCompletion.create(
                    model=ModelUtils.convert[self.AI_MODEL],
                    provider=provider,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_new_tokens,
                    temperature=float(self.AI_TEMPERATURE),
                    top_p=float(self.AI_TOP_P),
                    stream=False,
                )
                return validate_response(response=response)
            except Exception as e:
                logging.error(f"[Gpt4Free] Skip provider: {e}")
                if int(self.WAIT_AFTER_FAILURE) > 0:
                    time.sleep(int(self.WAIT_AFTER_FAILURE))
