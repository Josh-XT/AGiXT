import requests
import time
import logging
import uuid
import base64
import io
from PIL import Image

MODELS = {
    "HuggingFaceH4/starchat-beta": 8192,
    "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5": 1512,
    "bigcode/starcoderplus": 8192,
    "bigcode/starcoder": 8192,
    "bigcode/santacoder": 1512,
    "EleutherAI/gpt-neox-20b": 1512,
    "EleutherAI/gpt-neo-1.3B": 2048,
    "RedPajama-INCITE-Instruct-3B-v1": 2048,
}


class HuggingfaceProvider:
    def __init__(
        self,
        MODEL_PATH: str = "HuggingFaceH4/starchat-beta",
        HUGGINGFACE_API_KEY: str = None,
        HUGGINGFACE_API_URL: str = "https://api-inference.huggingface.co/models/{model}",
        STABLE_DIFFUSION_MODEL: str = "runwayml/stable-diffusion-v1-5",
        STABLE_DIFFUSION_API_URL: str = "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5",
        AI_MODEL: str = "starchat",
        stop=["<|end|>"],
        MAX_TOKENS: int = 1024,
        AI_TEMPERATURE: float = 0.7,
        MAX_RETRIES: int = 15,
        **kwargs,
    ):
        self.requirements = []
        self.MODEL_PATH = MODEL_PATH
        self.HUGGINGFACE_API_KEY = HUGGINGFACE_API_KEY
        self.HUGGINGFACE_API_URL = HUGGINGFACE_API_URL
        if (
            STABLE_DIFFUSION_MODEL != "runwayml/stable-diffusion-v1-5"
            and STABLE_DIFFUSION_API_URL.startswith(
                "https://api-inference.huggingface.co/models"
            )
        ):
            self.STABLE_DIFFUSION_API_URL = (
                f"https://api-inference.huggingface.co/models/{STABLE_DIFFUSION_MODEL}"
            )
        else:
            self.STABLE_DIFFUSION_API_URL = STABLE_DIFFUSION_API_URL
        self.AI_TEMPERATURE = AI_TEMPERATURE
        self.MAX_TOKENS = MAX_TOKENS
        self.AI_MODEL = AI_MODEL
        self.stop = stop
        self.MAX_RETRIES = MAX_RETRIES
        self.parameters = kwargs

    def get_url(self) -> str:
        return self.HUGGINGFACE_API_URL.replace("{model}", self.MODEL_PATH)

    def get_max_length(self):
        if self.MODEL_PATH in MODELS:
            return MODELS[self.MODEL_PATH]
        return 4096

    def get_max_new_tokens(self, input_length: int = 0) -> int:
        return min(self.get_max_length() - input_length, self.MAX_TOKENS)

    def request(self, inputs, **kwargs):
        payload = {"inputs": inputs, "parameters": {**kwargs}}
        headers = {}
        if self.HUGGINGFACE_API_KEY:
            headers["Authorization"] = f"Bearer {self.HUGGINGFACE_API_KEY}"

        tries = 0
        while True:
            tries += 1
            if tries > self.MAX_RETRIES:
                raise ValueError(f"Reached max retries: {self.MAX_RETRIES}")
            response = requests.post(self.get_url(), json=payload, headers=headers)
            if response.status_code == 429:
                logging.info(
                    f"Server Error {response.status_code}: Getting rate-limited / wait for {tries} seconds."
                )
                time.sleep(tries)
            elif response.status_code >= 500:
                logging.info(
                    f"Server Error {response.status_code}: {response.json()['error']} / wait for {tries} seconds"
                )
                time.sleep(tries)
            elif response.status_code != 200:
                raise ValueError(f"Error {response.status_code}: {response.text}")
            else:
                break

        content_type = response.headers["Content-Type"]
        if content_type == "application/json":
            return response.json()

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        result = self.request(
            prompt,
            temperature=self.AI_TEMPERATURE,
            max_new_tokens=self.get_max_new_tokens(tokens),
            return_full_text=False,
            stop=self.stop,
            **self.parameters,
        )[0]["generated_text"]
        if self.stop:
            for stop_seq in self.stop:
                find = result.find(stop_seq)
                if find >= 0:
                    result = result[:find]
        return result

    async def generate_image(
        self,
        prompt: str,
        filename: str = "",
    ) -> str:
        if filename == "":
            filename = f"{uuid.uuid4()}.png"
        image_path = f"./WORKSPACE/{filename}"
        headers = {}
        headers = {"Authorization": f"Bearer {self.HUGGINGFACE_API_KEY}"}
        try:
            response = requests.post(
                self.STABLE_DIFFUSION_API_URL,
                headers=headers,
                json={
                    "inputs": prompt,
                },
            )
            if self.HUGGINGFACE_API_KEY != "":
                image_data = response.content
            else:
                response = response.json()
                image_data = base64.b64decode(response["images"][-1])
            image = Image.open(io.BytesIO(image_data))
            logging.info(f"Image Generated for prompt: {prompt} at {image_path}.")
            image.save(image_path)
            encoded_image_data = base64.b64encode(image_data).decode("utf-8")
            return f"data:image/png;base64,{encoded_image_data}"
        except Exception as e:
            logging.error(f"Error generating image: {e}")
            return f"Error generating image: {e}"
