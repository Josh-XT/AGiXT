import time
import logging

try:
    import openai
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai"])
    import openai


class OpenaiProvider:
    def __init__(
        self,
        OPENAI_API_KEY: str = "",
        AI_MODEL: str = "gpt-3.5-turbo-16k-0613",
        AI_TEMPERATURE: float = 0.7,
        AI_TOP_P: float = 0.7,
        MAX_TOKENS: int = 16384,
        API_URI: str = "https://api.openai.com/v1",
        WAIT_BETWEEN_REQUESTS: int = 1,
        WAIT_AFTER_FAILURE: int = 3,
        stream: str = "false",
        **kwargs,
    ):
        self.requirements = ["openai"]
        self.AI_MODEL = AI_MODEL if AI_MODEL else "gpt-3.5-turbo-16k-0613"
        self.AI_TEMPERATURE = AI_TEMPERATURE if AI_TEMPERATURE else 0.7
        self.AI_TOP_P = AI_TOP_P if AI_TOP_P else 0.7
        self.MAX_TOKENS = MAX_TOKENS if MAX_TOKENS else 16000
        self.API_URI = API_URI if API_URI else "https://api.openai.com/v1"
        self.WAIT_AFTER_FAILURE = WAIT_AFTER_FAILURE if WAIT_AFTER_FAILURE else 3
        self.WAIT_BETWEEN_REQUESTS = (
            WAIT_BETWEEN_REQUESTS if WAIT_BETWEEN_REQUESTS else 1
        )
        if not stream:
            self.stream = False
        self.stream = True if str(stream).lower() == "true" else False
        openai.api_base = self.API_URI
        openai.api_key = OPENAI_API_KEY

    async def instruct(self, prompt, tokens: int = 0):
        max_new_tokens = int(self.MAX_TOKENS) - tokens
        if int(self.WAIT_BETWEEN_REQUESTS) > 0:
            time.sleep(int(self.WAIT_BETWEEN_REQUESTS))
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
                    stream=bool(self.stream),
                )
                if not self.stream:
                    return response.choices[0].text.strip()
                else:
                    answer = []
                    for event in response:
                        event_text = event["choices"][0]["text"]
                        if event_text:
                            answer.append(event_text.get("text", ""))
                        time.sleep(0.1)
                    new_response = " ".join(answer)
                    return new_response.strip()
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
                    stream=bool(self.stream),
                )
                if not self.stream:
                    return response.choices[0].message.content.strip()
                else:
                    answer = []
                    for event in response:
                        event_text = event["choices"][0]["delta"]
                        if event_text:
                            answer.append(event_text.get("content", ""))
                        time.sleep(0.1)
                    new_response = " ".join(answer)
                    return new_response.strip()
        except Exception as e:
            logging.info(f"OpenAI API Error: {e}")
            if int(self.WAIT_AFTER_FAILURE) > 0:
                time.sleep(int(self.WAIT_AFTER_FAILURE))
                return await self.instruct(prompt=prompt, tokens=tokens)
            return str(response)
