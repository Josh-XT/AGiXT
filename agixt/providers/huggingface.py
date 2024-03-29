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
        self.STABLE_DIFFUSION_API_URL = (
            f"https://api-inference.huggingface.co/models/{STABLE_DIFFUSION_MODEL}"
        )
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
        negative_prompt: str = "out of frame,lowres,text,error,cropped,worst quality,low quality,jpeg artifacts,ugly,duplicate,morbid,mutilated,out of frame,extra fingers,mutated hands,poorly drawn hands,poorly drawn face,mutation,deformed,blurry,dehydrated,bad anatomy,bad proportions,extra limbs,cloned face,disfigured,gross proportions,malformed limbs,missing arms,missing legs,extra arms,extra legs,fused fingers,too many fingers,long neck,username,watermark,signature",
        batch_size: int = 1,
        cfg_scale: int = 7,
        denoising_strength: int = 0,
        enable_hr: bool = False,
        eta: int = 0,
        firstphase_height: int = 0,
        firstphase_width: int = 0,
        height: int = 512,
        n_iter: int = 1,
        restore_faces: bool = True,
        s_churn: int = 0,
        s_noise: int = 1,
        s_tmax: int = 0,
        s_tmin: int = 0,
        sampler_index: str = "DPM++ SDE Karras",
        seed: int = -1,
        seed_resize_from_h: int = -1,
        seed_resize_from_w: int = -1,
        steps: int = 20,
        styles: list = [],
        subseed: int = -1,
        subseed_strength: int = 0,
        tiling: bool = False,
        width: int = 768,
    ) -> str:
        if filename == "":
            filename = f"{uuid.uuid4()}.png"
        image_path = f"./WORKSPACE/{filename}"
        headers = {}
        if (
            self.STABLE_DIFFUSION_API_URL.startswith(
                "https://api-inference.huggingface.co/models"
            )
            and self.HUGGINGFACE_API_KEY != ""
        ):
            headers = {"Authorization": f"Bearer {self.HUGGINGFACE_API_KEY}"}
            generation_settings = {
                "inputs": prompt,
            }
        else:
            self.STABLE_DIFFUSION_API_URL = (
                f"{self.STABLE_DIFFUSION_API_URL}/sdapi/v1/txt2img"
            )
            generation_settings = {
                "prompt": prompt,
                "negative_prompt": (
                    negative_prompt
                    if negative_prompt
                    else "out of frame,lowres,text,error,cropped,worst quality,low quality,jpeg artifacts,ugly,duplicate,morbid,mutilated,out of frame,extra fingers,mutated hands,poorly drawn hands,poorly drawn face,mutation,deformed,blurry,dehydrated,bad anatomy,bad proportions,extra limbs,cloned face,disfigured,gross proportions,malformed limbs,missing arms,missing legs,extra arms,extra legs,fused fingers,too many fingers,long neck,username,watermark,signature"
                ),
                "batch_size": batch_size if batch_size else 1,
                "cfg_scale": cfg_scale if cfg_scale else 7,
                "denoising_strength": denoising_strength if denoising_strength else 0,
                "enable_hr": enable_hr if enable_hr else False,
                "eta": eta if eta else 0,
                "firstphase_height": firstphase_height if firstphase_height else 0,
                "firstphase_width": firstphase_width if firstphase_width else 0,
                "height": height if height else 1080,
                "n_iter": n_iter if n_iter else 1,
                "restore_faces": restore_faces if restore_faces else False,
                "s_churn": s_churn if s_churn else 0,
                "s_noise": s_noise if s_noise else 1,
                "s_tmax": s_tmax if s_tmax else 0,
                "s_tmin": s_tmin if s_tmin else 0,
                "sampler_index": sampler_index if sampler_index else "Euler a",
                "seed": seed if seed else -1,
                "seed_resize_from_h": seed_resize_from_h if seed_resize_from_h else -1,
                "seed_resize_from_w": seed_resize_from_w if seed_resize_from_w else -1,
                "steps": steps if steps else 20,
                "styles": styles if styles else [],
                "subseed": subseed if subseed else -1,
                "subseed_strength": subseed_strength if subseed_strength else 0,
                "tiling": tiling if tiling else False,
                "width": width if width else 1920,
            }
        try:
            response = requests.post(
                self.STABLE_DIFFUSION_API_URL,
                headers=headers,
                json=generation_settings,  # Use the 'json' parameter instead
            )
            if self.HUGGINGFACE_API_KEY != "":
                image_data = response.content
            else:
                response = response.json()
                image_data = base64.b64decode(response["images"][-1])

            image = Image.open(io.BytesIO(image_data))
            logging.info(f"Image Generated for prompt: {prompt} at {image_path}.")
            image.save(image_path)  # Save the image locally if required

            # Convert image_data to base64 string
            encoded_image_data = base64.b64encode(image_data).decode("utf-8")
            return f"#GENERATED_IMAGE:{encoded_image_data}"
        except Exception as e:
            logging.error(f"Error generating image: {e}")
            return f"Error generating image: {e}"


if __name__ == "__main__":
    import asyncio

    async def run_test():
        response = await HuggingfaceProvider().inference(
            "<|system|>\n<|end|>\n<|user|>\nHello<|end|>\n<|assistant|>\n"
        )
        print(f"Test: {response}")
        response = await HuggingfaceProvider(
            "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5", stop=["<|endoftext|>"]
        ).inference("<|prompter|>Hello<|endoftext|><|assistant|>")
        print(f"Test2: {response}")

    asyncio.run(run_test())
