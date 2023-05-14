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
        self.providers = [Provider.UseLess, Provider.You]

    def instruct(self, prompt):
        for provider in self.providers:
            try:
                if provider == gpt4free.Provider.UseLess:
                    response = gpt4free.Completion.create(
                        provider,
                        prompt=prompt,
                        model=self.AI_MODEL,
                        systemMessage="",
                    )
                    if "text" in response:
                        response = response["text"]
                    if "status" in response and response["status"] == "Fail":
                        response = None
                elif provider == gpt4free.Provider.You:
                    response = gpt4free.Completion.create(provider, prompt=prompt)
                    if response == "Unable to fetch the response, Please try again.":
                        response = None
                else:
                    response = gpt4free.Completion.create(
                        provider,
                        prompt=prompt,
                        model=self.AI_MODEL,
                    )
                if not response:
                    raise Exception(f"No model result with: {provider}")
                return response
            except Exception as e:
                if provider == self.providers[-1]:
                    raise Exception(f"Model error: {e}", e)
                else:
                    print(f"Model error: {e}")
