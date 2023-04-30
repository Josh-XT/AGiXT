import openai


class AIProvider:
    def __init__(
        self,
        OPENAI_API_KEY: str = "",
        AI_MODEL: str = "gpt-3.5-turbo",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4096,
    ):
        self.requirements = ["openai"]
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        openai.api_key = OPENAI_API_KEY

    def instruct(self, prompt):
        if not self.AI_MODEL.startswith("gpt-"):
            # Use completion API
            response = openai.Completion.create(
                engine=self.AI_MODEL,
                prompt=prompt,
                temperature=self.AI_TEMPERATURE,
                max_tokens=int(self.MAX_TOKENS),
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
            )
            return response.choices[0].text.strip()
        else:
            # Use chat completion API
            messages = [{"role": "system", "content": prompt}]
            response = openai.ChatCompletion.create(
                model=self.AI_MODEL,
                messages=messages,
                temperature=self.AI_TEMPERATURE,
                max_tokens=int(self.MAX_TOKENS),
                n=1,
                stop=None,
            )
            return response.choices[0].message.content.strip()
