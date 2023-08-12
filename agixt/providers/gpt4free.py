import logging

try:
    from g4f import Provider, ChatCompletion
    from g4f.models import ModelUtils
except ImportError:
    import sys, subprocess

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "g4f",
        ]
    )
    from g4f import Provider, ChatCompletion
    from g4f.models import ModelUtils

providers = [
    # Working:
    Provider.GetGpt,
    Provider.ChatgptAi,
    Provider.H2o,
    # Works sometimes:
    Provider.Aichat,
    Provider.AiService,
    # Not working today:
    Provider.Ails,
    Provider.AItianhu,
    Provider.Bing,
    Provider.ChatgptLogin,
    Provider.DeepAi,
    # Provider.DfeHub, endless loop
    Provider.EasyChat,
    Provider.Lockchat,
    Provider.Theb,
    Provider.Vercel,
    Provider.You,
    Provider.Yqcloud,
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
        **kwargs,
    ):
        self.requirements = ["gpt4free"]
        self.model = AI_MODEL

    async def instruct(self, prompt, tokens: int = 0):
        for provider in providers:
            if not provider.working:
                continue
            try:
                logging.info(f"[Gpt4Free] Use provider: {provider.__name__}")
                if self.model not in provider.model:
                    model = (
                        provider.model
                        if type(provider.model) == str
                        else provider.model[0]
                    )
                    logging.info(f"[Gpt4Free] Use model: {model}")
                else:
                    model = self.model
                response = ChatCompletion.create(
                    model=ModelUtils.convert[self.model],
                    provider=provider,
                    messages=[{"role": "user", "content": prompt}],
                )
                return validate_response(response)
            except Exception as e:
                logging.error(f"[Gpt4Free] Skip provider: {e}")


if __name__ == "__main__":
    # Test provider class
    import asyncio

    async def run_test():
        response = await Gpt4freeProvider().instruct("Hello")
        print(f"Class test: {response}")

    asyncio.run(run_test())

    # Test all providers
    for provider in providers:
        if not provider.working:
            continue
        try:
            print(f"Use provider: {provider.__name__}")
            model = provider.model if type(provider.model) == str else provider.model[0]
            print(f"Use model: {model}")
            response = ChatCompletion.create(
                model=ModelUtils.convert[model],
                provider=provider,
                messages=[{"role": "user", "content": "Hello"}],
            )
            print(f"Response: {validate_response(response)}")
        except Exception as e:
            print(f"{e.__class__.__name__}: {e}")
