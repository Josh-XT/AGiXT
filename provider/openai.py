import openai


class OpenaiProvider:
    def __init__(
        self,
        OPENAI_API_KEY: str = "",
        AI_MODEL: str = "gpt-3.5-turbo",
        AI_TEMPERATURE: float = 0.7,
        MAX_TOKENS: int = 4096,
        **kwargs
    ):
        self.requirements = ["openai"]
        self.AI_MODEL = AI_MODEL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        openai.api_key = OPENAI_API_KEY

    def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = int(self.MAX_TOKENS) - tokens
        if not self.AI_MODEL.startswith("gpt-"):
            # Use completion API
            response = openai.Completion.create(
                engine=self.AI_MODEL,
                prompt=prompt,
                temperature=float(self.AI_TEMPERATURE),
                max_tokens=max_new_tokens,
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
                temperature=float(self.AI_TEMPERATURE),
                max_tokens=max_new_tokens,
                n=1,
                stop=None,
            )
            return response.choices[0].message.content.strip()
