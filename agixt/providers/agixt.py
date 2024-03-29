import uuid
import requests
import base64
import io

try:
    from PIL import Image
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow"])
    from PIL import Image
import logging


# This will create a hive agent that will create memories for itself and each agent in the rotation.
# If one agent fails, it will move on to the next agent in the rotation.
class AgixtProvider:
    def __init__(
        self,
        agents: list = [],
        MAX_TOKENS: int = 16000,
        STABLE_DIFFUSION_API_URL="https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5",
        ELEVENLABS_API_KEY: str = "",
        VOICE: str = "Josh",
        **kwargs,
    ):
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        self.MAX_TOKENS = int(MAX_TOKENS) if int(MAX_TOKENS) != 0 else 16000
        self.agents = self.ApiClient.get_agents() if agents == [] else agents
        self.STABLE_DIFFUSION_API_URL = STABLE_DIFFUSION_API_URL
        self.ELEVENLABS_API_KEY = ELEVENLABS_API_KEY
        self.ELEVENLABS_VOICE = VOICE

    async def inference(self, prompt, tokens: int = 0, images: list = []):
        for agent in self.agents:
            try:
                return self.ApiClient.prompt_agent(
                    agent_name=agent,
                    prompt="Custom Input",
                    prompt_args={"user_input": prompt},
                )
            except Exception as e:
                print(f"[AGiXT] {agent} failed. Error: {e}. Moving on to next agent.")
                continue
        return "No agents available"

    # Auto1111 Stable Diffusion API
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
            response = response.json()
            image_data = base64.b64decode(response["images"][-1])
            image = Image.open(io.BytesIO(image_data))
            logging.info(f"Image Generated for prompt: {prompt} at {image_path}.")
            image.save(image_path)  # Save the image locally if required
            # Convert image_data to base64 string
            encoded_image_data = base64.b64encode(image_data).decode("utf-8")
            return f"data:image/png;base64,{encoded_image_data}"
        except Exception as e:
            logging.error(f"Error generating image: {e}")
            return f"Error generating image: {e}"

    async def text_to_speech(self, text: str) -> bool:
        headers = {
            "Content-Type": "application/json",
            "xi-api-key": self.ELEVENLABS_VOICE,
        }
        try:
            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.ELEVENLABS_VOICE}",
                headers=headers,
                json={"text": text},
            )
            response.raise_for_status()
        except:
            self.ELEVENLABS_VOICE = "ErXwobaYiN019PkySvjV"
            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.ELEVENLABS_VOICE}",
                headers=headers,
                json={"text": text},
            )
        if response.status_code == 200:
            # Return the base64 audio/wav
            return f"data:audio/wav;base64,{response.content.decode('utf-8')}"
        else:
            return "Failed to generate audio."
