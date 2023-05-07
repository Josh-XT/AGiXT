import os
import glob
from dotenv import load_dotenv

load_dotenv()


class Config:
    def __init__(self):
        self.WORKING_DIRECTORY = os.getenv("WORKING_DIRECTORY", "WORKSPACE")
        self._create_directory_if_not_exists(self.WORKING_DIRECTORY)
        self.WORKING_DIRECTORY_RESTRICTED = os.getenv(
            "WORKING_DIRECTORY_RESTRICTED", True
        )
        # Extensions Configuration

        # OpenAI
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

        # Bard
        self.BARD_TOKEN = os.getenv("BARD_TOKEN")

        # Huggingface
        self.HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
        self.HUGGINGFACE_AUDIO_TO_TEXT_MODEL = os.getenv(
            "HUGGINGFACE_AUDIO_TO_TEXT_MODEL", "facebook/wav2vec2-large-960h-lv60-self"
        )

        # Selenium
        self.SELENIUM_WEB_BROWSER = os.getenv("SELENIUM_WEB_BROWSER", "chrome").lower()

        # Twitter
        self.TW_CONSUMER_KEY = os.getenv("TW_CONSUMER_KEY")
        self.TW_CONSUMER_SECRET = os.getenv("TW_CONSUMER_SECRET")
        self.TW_ACCESS_TOKEN = os.getenv("TW_ACCESS_TOKEN")
        self.TW_ACCESS_TOKEN_SECRET = os.getenv("TW_ACCESS_TOKEN_SECRET")

        # Github
        self.GITHUB_API_KEY = os.getenv("GITHUB_API_KEY")
        self.GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

        # Sendgrid
        self.SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
        self.SENDGRID_EMAIL = os.getenv("SENDGRID_EMAIL")

        # Microsft 365
        self.MICROSOFT_365_CLIENT_ID = os.getenv("MICROSOFT_365_CLIENT_ID")
        self.MICROSOFT_365_CLIENT_SECRET = os.getenv("MICROSOFT_365_CLIENT_SECRET")
        self.MICROSOFT_365_REDIRECT_URI = os.getenv("MICROSOFT_365_REDIRECT_URI")

        # SearXNG - List of these at https://searx.space/
        self.SEARXNG_INSTANCE_URL = os.getenv(
            "SEARXNG_INSTANCE_URL", "https://searx.work"
        )

        # Discord
        self.DISCORD_API_KEY = os.getenv("DISCORD_API_KEY")

        # Voice (Choose one: ElevenLabs, Brian, Mac OS)
        # Elevenlabs
        self.ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        self.ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "Josh")
        # Mac OS TTS
        self.USE_MAC_OS_TTS = os.getenv("USE_MAC_OS_TTS", "false").lower()

        # Brian TTS
        self.USE_BRIAN_TTS = os.getenv("USE_BRIAN_TTS", "true").lower()

    def _create_directory_if_not_exists(self, directory):
        if not os.path.exists(directory):
            os.makedirs(directory)

    def get_providers(self):
        providers = []
        for provider in glob.glob("provider/*.py"):
            if "__init__.py" not in provider:
                providers.append(os.path.splitext(os.path.basename(provider))[0])
        return providers

    def get_agents(self):
        memories_dir = "agents"
        if not os.path.exists(memories_dir):
            os.makedirs(memories_dir)
        agents = []
        for file in os.listdir(memories_dir):
            if file.endswith(".yaml"):
                agents.append(file.replace(".yaml", ""))
        output = []
        if agents:
            for agent in agents:
                try:
                    agent_instance = self.agent_instances[agent]
                    status = agent_instance.get_status()
                except:
                    status = False
                output.append({"name": agent, "status": status})
        return output
