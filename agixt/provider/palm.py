import google.generativeai as palm


class PalmProvider:
    def __init__(
        self,
        AI_MODEL: str = "default",
        PALM_API_KEY: str = "",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4000,
        **kwargs,
    ):
        self.requirements = []
        self.PALM_API_KEY = PALM_API_KEY
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        palm.configure(api_key=self.PALM_API_KEY)

    def instruct(self, prompt, tokens: int = 0):
        new_max_tokens = int(self.MAX_TOKENS) - tokens
        completion = palm.generate_text(
            model="models/text-bison-001",
            prompt=prompt,
            temperature=float(self.AI_TEMPERATURE),
            max_output_tokens=new_max_tokens,
        )
        return completion.result
