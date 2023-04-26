import openai
from Config import Config

CFG = Config()


class AIProvider:
    def __init__(self):
        openai.api_key = CFG.OPENAI_API_KEY
        if "gpt-4" in CFG.AI_MODEL.lower():
            print(
                "\033[91m\033[1m"
                + "\n*****USING GPT-4. POTENTIALLY EXPENSIVE. MONITOR YOUR COSTS*****"
                + "\033[0m\033[0m"
            )

    def instruct(self, prompt):
        if not CFG.AI_MODEL.startswith("gpt-"):
            # Use completion API
            response = openai.Completion.create(
                engine=CFG.AI_MODEL,
                prompt=prompt,
                temperature=CFG.AI_TEMPERATURE,
                max_tokens=int(CFG.MAX_TOKENS),
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
            )
            return response.choices[0].text.strip()
        else:
            # Use chat completion API
            messages = [{"role": "system", "content": prompt}]
            response = openai.ChatCompletion.create(
                model=CFG.AI_MODEL,
                messages=messages,
                temperature=CFG.AI_TEMPERATURE,
                max_tokens=int(CFG.MAX_TOKENS),
                n=1,
                stop=None,
            )
            return response.choices[0].message.content.strip()
