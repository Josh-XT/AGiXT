import gpt4free


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
        # This will work when more than 2 of the 5 providers are working
        # providers = gpt4free.Provider._member_names_
        providers = ["You", "Useless"]
        for provider in providers:
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
                if len(self.FAILED_PROVIDERS) == len(providers):
                    self.FAILED_PROVIDERS = []
                try:
                    response = self.instruct(prompt, tokens)
                except:
                    response = self.instruct(prompt, tokens)
                return response
