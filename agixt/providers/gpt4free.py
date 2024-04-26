from g4f.client import Client


class Gpt4freeProvider:
    def __init__(
        self,
        AI_MODEL: str = "gpt-4-turbo",
        **kwargs,
    ):
        self.requirements = ["g4f"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-4-turbo"

    @staticmethod
    def services():
        return ["llm"]

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        models = [
            "gpt-4-turbo",
            "gpt-4",
            "mixtral-8x7b",
            "mistral-7b",
        ]
        client = Client()
        try:
            response = client.chat.completions.create(
                model=self.AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except:
            for model in models:
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    return response.choices[0].message.content
                except:
                    continue
        return "Unable to retrieve response."
