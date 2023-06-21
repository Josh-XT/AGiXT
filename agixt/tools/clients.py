import time
import requests
import openai
from huggingface_hub import HfFolder

class AgentClient:
    def generate(self, prompt, stop=[]):
        raise NotImplementedError
    
class OpenAiAgentClient(AgentClient):
    def __init__(
        self,
        model="gpt-3.5-turbo-16k",
        api_key=None,
        api_base=None
    ):
        if api_key is not None:
            openai.api_key = api_key
        if api_base:
            openai.api_base = api_base
        self.model = model
        self.stop = ["Human:", "====="]

    def generate(self, prompt, stop=None):
        result = openai.ChatCompletion.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            stop=stop or self.stop,
        )
        return result["choices"][0]["message"]["content"]
    
class HfAgentClient(AgentClient):
    def __init__(
        self,
        url_endpoint,
        token=None
    ):
        self.url_endpoint = url_endpoint
        if token is None:
            self.token = f"Bearer {HfFolder().get_token()}"
        elif token.startswith("Bearer") or token.startswith("Basic"):
            self.token = token
        else:
            self.token = f"Bearer {token}"

    def generate(self, prompt, stop=None):
        headers = {"Authorization": self.token}
        inputs = {
            "inputs": prompt,
            "parameters": {"max_new_tokens": 1028, "return_full_text": False, "stop": stop},
        }

        response = requests.post(self.url_endpoint, json=inputs, headers=headers)
        if response.status_code == 429:
            print("Getting rate-limited, waiting a tiny bit before trying again.")
            time.sleep(1)
            return self.generate(prompt, stop)
        elif response.status_code != 200:
            raise ValueError(f"Error {response.status_code}: {response.json()}")

        result = response.json()[0]["generated_text"]
        # Inference API returns the stop sequence
        for stop_seq in stop:
            if result.endswith(stop_seq):
                result = result[: -len(stop_seq)]
        return result