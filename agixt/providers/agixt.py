import requests


# This will create a hive agent that will create memories for itself and each agent in the rotation.
# If one agent fails, it will move on to the next agent in the rotation.
class AgixtProvider:
    def __init__(
        self,
        agents: list = [],
        ELEVENLABS_API_KEY: str = "",
        VOICE: str = "Josh",
        **kwargs,
    ):
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        self.MAX_TOKENS = 8192
        self.agents = self.ApiClient.get_agents() if agents == [] else agents
        self.ELEVENLABS_API_KEY = ELEVENLABS_API_KEY
        self.ELEVENLABS_VOICE = VOICE

    @staticmethod
    def services():
        return ["llm", "tts"]

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
            return response.content
        else:
            return "Failed to generate audio."
