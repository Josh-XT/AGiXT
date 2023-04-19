import os
import glob
from dotenv import load_dotenv
load_dotenv()

class Config():
    def __init__(self):
        # General Configuration
        self.AGENT_NAME = os.getenv("AGENT_NAME", "Agent-LLM")
        self.AGENTS = glob.glob(os.path.join("memories", "*.yaml"))
        # Goal Configuation
        self.OBJECTIVE = os.getenv("OBJECTIVE", "Solve world hunger")
        self.INITIAL_TASK = os.getenv("INITIAL_TASK", "Develop a task list")
        
        # AI Configuration
        self.AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").lower()

        # AI_PROVIDER_URI is only needed for custom AI providers such as Oobabooga Text Generation Web UI
        self.AI_PROVIDER_URI = os.getenv("AI_PROVIDER_URI", "http://127.0.0.1:7860")
        self.LLAMACPP_PATH = os.getenv("LLAMACPP_PATH", "llama/main")

        # Bing Conversation Style if using Bing. Options are creative, balanced, and precise
        self.BING_CONVERSATION_STYLE = os.getenv("BING_CONVERSATION_STYLE", "creative").lower()

        # ChatGPT Configuration
        self.CHATGPT_USERNAME = os.getenv("CHATGPT_USERNAME")
        self.CHATGPT_PASSWORD = os.getenv("CHATGPT_PASSWORD")

        self.COMMANDS_ENABLED = os.getenv("COMMANDS_ENABLED", "true").lower()
        self.WORKING_DIRECTORY = os.getenv("WORKING_DIRECTORY", "WORKSPACE")
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY)
        
        # Memory Settings
        self.NO_MEMORY = os.getenv("NO_MEMORY", "false").lower()
        self.USE_LONG_TERM_MEMORY_ONLY = os.getenv("USE_LONG_TERM_MEMORY_ONLY", "false").lower()

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

        # Sendgrid
        self.SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
        self.SENDGRID_EMAIL = os.getenv("SENDGRID_EMAIL")

        # Microsft 365
        self.MICROSOFT_365_CLIENT_ID = os.getenv("MICROSOFT_365_CLIENT_ID")
        self.MICROSOFT_365_CLIENT_SECRET = os.getenv("MICROSOFT_365_CLIENT_SECRET")
        self.MICROSOFT_365_REDIRECT_URI = os.getenv("MICROSOFT_365_REDIRECT_URI")

        # Voice (Choose one: ElevenLabs, Brian, Mac OS)
        # Elevenlabs
        self.ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        self.ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "Josh")
        # Mac OS TTS
        self.USE_MAC_OS_TTS = os.getenv("USE_MAC_OS_TTS", "false").lower()

        # Brian TTS
        self.USE_BRIAN_TTS = os.getenv("USE_BRIAN_TTS", "true").lower()