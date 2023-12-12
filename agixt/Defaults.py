import os
from dotenv import load_dotenv

load_dotenv()
DEFAULT_USER = os.getenv("DEFAULT_USER", "USER")

DEFAULT_SETTINGS = {
    "provider": "gpt4free",
    "embedder": "default",
    "AI_MODEL": "gpt-3.5-turbo",
    "AI_TEMPERATURE": "0.7",
    "AI_TOP_P": "1",
    "MAX_TOKENS": "4096",
    "helper_agent_name": "gpt4free",
    "WEBSEARCH_TIMEOUT": 0,
    "WAIT_BETWEEN_REQUESTS": 1,
    "WAIT_AFTER_FAILURE": 3,
    "stream": False,
    "WORKING_DIRECTORY": "./WORKSPACE",
    "WORKING_DIRECTORY_RESTRICTED": True,
    "AUTONOMOUS_EXECUTION": True,
    "PERSONA": "",
}
