import os
from dotenv import load_dotenv
load_dotenv()

class Config():
    def __init__(self):
        # General Configuration
        self.AGENT_NAME = os.getenv("AGENT_NAME", "Agent-LLM")
        
        # Goal Configuation
        self.OBJECTIVE = os.getenv("OBJECTIVE", "Solve world hunger")
        self.INITIAL_TASK = os.getenv("INITIAL_TASK", "Develop a task list")
        
        # AI Configuration
        self.AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").lower()
        self.COMMANDS_ENABLED = os.getenv("COMMANDS_ENABLED", "true").lower() == "true"
        self.WORKING_DIRECTORY = os.getenv("WORKING_DIRECTORY", "WORKSPACE")
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY)
        # Model configuration
        self.AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo").lower()
        self.AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", 0.4))
        self.MAX_TOKENS = os.getenv("MAX_TOKENS", 2000)
        
        # Extensions Configuration

        # OpenAI
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

        # Huggingface
        self.HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
        self.HUGGINGFACE_AUDIO_TO_TEXT_MODEL = os.getenv("HUGGINGFACE_AUDIO_TO_TEXT_MODEL", "facebook/wav2vec2-large-960h-lv60-self")
        
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

        # Voice (Choose one: ElevenLabs, Brian, Mac OS)
        # Elevenlabs
        self.ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        self.ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "Josh")
        # Mac OS TTS
        self.USE_MAC_OS_TTS = os.getenv("USE_MAC_OS_TTS", "false").lower() == "false"

        # Brian TTS
        self.USE_BRIAN_TTS = os.getenv("USE_BRIAN_TTS", "true").lower() == "true"