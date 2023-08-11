import logging

try:
    from g4f import Provider, ModelUtils, ChatCompletion
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
    from g4f import Provider, ModelUtils, ChatCompletion

providers = [
    # Working:
    Provider.GetGpt,
    Provider.ChatgptAi,
    Provider.H2o,
    # Works sometimes:
    Provider.Aichat,
    Provider.AiService,
    # Not working today:
    Provider.Yqcloud,
    Provider.Ails,
    Provider.AItianhu,
    Provider.Bing,
    Provider.ChatgptLogin,
    Provider.DeepAi,
    # Provider.DfeHub, endless loop
    # Provider.EasyChat, ERROR pointing to g4f code
    Provider.Lockchat,
    Provider.Theb,
    Provider.Vercel,
    Provider.You,
]


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
                    if type(provider.model) == str:
                        model = provider.model
                    else:
                        model = provider.model[0]
                    logging.info(f"[Gpt4Free] Use model: {model}")
                else:
                    model = self.model
                response = ChatCompletion.create(
                    model=ModelUtils.convert[self.model],
                    provider=provider,
                    messages=[{"role": "user", "content": prompt}],
                )
                if not response:
                    logging.info(f"[Gpt4Free] Skip provider: Empty response")
                    continue
                elif not isinstance(response, str):
                    logging.info(f"[Gpt4Free] Skip provider: Response is not a string")
                    continue
                elif (
                    response
                    in (
                        "Vercel is currently not working.",
                        "Unable to fetch the response, Please try again.",
                    )
                    or '{"error":{"message":"Hey! The webpage has been updated.'
                    in response
                ):  # Ails
                    logging.info(f"[Gpt4Free] Skip provider: {response}")
                    continue
                else:
                    return response
            except Exception as e:
                logging.info(f"[Gpt4Free] Exception: {e}")
            provider.working = False


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
            if type(provider.model) == str:
                model = provider.model
            else:
                model = provider.model[0]
            print(f"Use model: {model}")
            response = ChatCompletion.create(
                model=ModelUtils.convert[model],
                provider=provider,
                messages=[{"role": "user", "content": "Hello"}],
            )
            print(f"Response: {response}")
        except Exception as e:
            print(f"{e.__class__.__name__}: {e}")
