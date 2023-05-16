import gpt4free
from gpt4free import Provider


class Gpt4freeProvider:
    def __init__(
        self,
        AI_MODEL: str = "gpt-4",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4000,
        **kwargs,
    ):
        self.requirements = ["gpt4free"]
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.FAILED_PROVIDERS = []

    def instruct(self, prompt, tokens: int = 0):
        providers = list(Provider)
        for provider in providers:
            try:
                if provider not in self.FAILED_PROVIDERS:
                    response = gpt4free.Completion.create(
                        provider,
                        prompt=prompt,
                        model=self.AI_MODEL,
                        systemMessage="",
                    )
                    if "text" in response:
                        response = response["text"]
                    if "status" in response and response["status"] == "Fail":
                        self.FAILED_PROVIDERS.append(provider)
                        response = self.instruct(prompt, tokens)
                    if response == "Unable to fetch the response, Please try again.":
                        self.FAILED_PROVIDERS.append(provider)
                        response = self.instruct(prompt, tokens)
                return response
            except:
                self.FAILED_PROVIDERS.append(provider)
                if len(self.FAILED_PROVIDERS) == len(providers):
                    self.FAILED_PROVIDERS = []
                try:
                    response = self.instruct(prompt, tokens)
                except:
                    response = self.instruct(prompt, tokens)
                return response
