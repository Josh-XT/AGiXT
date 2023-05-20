import gpt4free
import time


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
        self.providers = ["DeepAI", "Useless", "You"]

    def instruct(self, prompt, tokens: int = 0):
        while True:  # Keep looping until we get a valid response
            for provider in self.providers:
                if provider in self.FAILED_PROVIDERS:
                    continue

                try:
                    response = gpt4free.Completion.create(
                        getattr(gpt4free.Provider, provider),
                        prompt=prompt,
                    )

                    if "text" in response:
                        response = response["text"]

                    # If the response is a failure, add the provider to the failed list and continue the loop
                    if "status" in response and response["status"] == "Fail":
                        self.FAILED_PROVIDERS.append(provider)
                        print(f"Failed to use {provider}")
                        continue

                    if response == "Unable to fetch the response, Please try again.":
                        self.FAILED_PROVIDERS.append(provider)
                        print(f"Failed to use {provider}")
                        continue

                    # If the response is valid, return it
                    return response

                except:
                    print(f"Failed to use {provider}")
                    self.FAILED_PROVIDERS.append(provider)

            # If all providers failed
            if len(self.FAILED_PROVIDERS) == len(self.providers):
                self.FAILED_PROVIDERS = []  # Reset the list
                print("All providers failed, trying again in 10 seconds")
                time.sleep(10)
