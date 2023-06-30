import openai
import time
import logging


class OpenaiProvider:
    def __init__(
        self,
        OPENAI_API_KEY: str = "",
        AI_MODEL: str = "gpt-3.5-turbo-16k-0613",
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        MAX_TOKENS: int = 16384,
        API_URI: str = "https://api.openai.com/v1",
        **kwargs,
    ):
        self.requirements = ["openai"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-3.5-turbo-16k-0613"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 16384
        self.API_URI = API_URI
        openai.api_base = self.API_URI
        openai.api_key = OPENAI_API_KEY

    async def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = int(self.MAX_TOKENS) - tokens
        try:
            if not self.AI_MODEL.startswith("gpt-"):
                # Use completion API
                response = openai.Completion.create(
                    engine=self.AI_MODEL,
                    prompt=prompt,
                    temperature=float(self.AI_TEMPERATURE),
                    max_tokens=max_new_tokens,
                    top_p=float(self.AI_TOP_P),
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
                    top_p=float(self.AI_TOP_P),
                    n=1,
                    stop=None,
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            logging.info(f"OpenAI API Error: {e}")
            time.sleep(3)
            return await self.instruct(prompt=prompt, tokens=tokens)
