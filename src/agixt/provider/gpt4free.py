import gpt4free
import time
import itertools


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
        self.providers = itertools.cycle(["DeepAI", "Useless", "You"])

    def instruct(self, prompt, tokens: int = 0):
        provider = next(self.providers)
        try:
            if provider not in self.FAILED_PROVIDERS:
                response = gpt4free.Completion.create(
                    getattr(gpt4free.Provider, provider),
                    prompt=prompt,
                )
                if "text" in response:
                    response = response["text"]
                if "status" in response and response["status"] == "Fail":
                    self.FAILED_PROVIDERS.append(provider)
                    print(f"Failed to use {provider}")
                    response = self.instruct(prompt, tokens)
                if response == "Unable to fetch the response, Please try again.":
                    self.FAILED_PROVIDERS.append(provider)
                    print(f"Failed to use {provider}")
                    response = self.instruct(prompt, tokens)
            return response
        except:
            print(f"Failed to use {provider}")
            self.FAILED_PROVIDERS.append(provider)
            if (
                len(self.FAILED_PROVIDERS) == 3
            ):  # adjust this value to the number of your providers
                self.FAILED_PROVIDERS = []
                print("All providers failed, trying again in 10 seconds")
                time.sleep(10)
            response = self.instruct(prompt, tokens)
            return response
