import gpt4free


class Gpt4freeProvider:
    def __init__(
        self,
        AI_MODEL: str = "gpt-4",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4096,
        **kwargs
    ):
        self.requirements = ["gpt4free"]
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS

    def instruct(self, prompt):
        response = gpt4free.Completion.create(
            gpt4free.Provider.UseLess, prompt=prompt, model=self.AI_MODEL
        )
        return response["text"]
