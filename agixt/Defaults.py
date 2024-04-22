import os
from dotenv import load_dotenv

load_dotenv()
DEFAULT_USER = os.getenv("DEFAULT_USER", "USER")

DEFAULT_SETTINGS = {
    "provider": "gpt4free",
    "mode": "prompt",
    "prompt_category": "Default",
    "prompt_name": "Chat",
    "embeddings_provider": "default",
    "tts_provider": "default",
    "transcription_provider": "default",
    "translation_provider": "default",
    "image_provider": "default",
    "VOICE": "Brian",
    "AI_MODEL": "mixtral-8x7b",
    "AI_TEMPERATURE": "0.7",
    "AI_TOP_P": "1",
    "MAX_TOKENS": "4096",
    "helper_agent_name": "gpt4free",
    "websearch": False,
    "websearch_depth": 3,
    "WEBSEARCH_TIMEOUT": 0,
    "WAIT_BETWEEN_REQUESTS": 1,
    "WAIT_AFTER_FAILURE": 3,
    "WORKING_DIRECTORY": "./WORKSPACE",
    "WORKING_DIRECTORY_RESTRICTED": True,
    "AUTONOMOUS_EXECUTION": True,
    "PERSONA": "",
}
