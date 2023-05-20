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
        self.providers = gpt4free.Provider._member_names_
        self.providers.sort()

    def instruct(self, prompt, tokens: int = 0):
        final_response = None
        while final_response is None:
            for provider in self.providers:
                if provider not in self.FAILED_PROVIDERS:
                    try:
                        response = gpt4free.Completion.create(
                            getattr(gpt4free.Provider, provider),
                            prompt=prompt,
                        )
                        if "text" in response:
                            final_response = response["text"]
                        if "status" in response and response["status"] == "Fail":
                            self.FAILED_PROVIDERS.append(provider)
                            print(f"Failed to use {provider}")
                            final_response = None
                        elif (
                            response
                            == "Unable to fetch the response, Please try again."
                        ):
                            self.FAILED_PROVIDERS.append(provider)
                            print(f"Failed to use {provider}")
                            final_response = None
                        else:
                            final_response = response
                    except:
                        print(f"Failed to use {provider}")
                        self.FAILED_PROVIDERS.append(provider)
                        final_response = None

                if final_response:
                    if len(final_response) > 1:
                        return final_response

            if len(self.FAILED_PROVIDERS) == len(self.providers):
                self.FAILED_PROVIDERS = []
                print(
                    "All providers failed, sleeping for 10 seconds before trying again..."
                )
                time.sleep(10)
