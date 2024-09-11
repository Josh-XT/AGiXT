import os
import json
import tiktoken
from dotenv import load_dotenv

load_dotenv()


def getenv(var_name: str):
    default_values = {
        "AGIXT_URI": "http://localhost:7437",
        "AGIXT_API_KEY": None,
        "EZLOCALAI_URI": "http://localhost:8091/v1/",
        "EZLOCALAI_API_KEY": "",
        "LLM_MAX_TOKENS": 8192,
        "ALLOWED_DOMAINS": "*",
        "WORKING_DIRECTORY": os.path.join(os.getcwd(), "WORKSPACE"),
        "APP_NAME": "AGiXT",
        "EMAIL_SERVER": "",
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "%(asctime)s | %(levelname)s | %(message)s",
        "UVICORN_WORKERS": 10,
        "DATABASE_TYPE": "postgresql",
        "DATABASE_NAME": "postgres",
        "DATABASE_USER": "postgres",
        "DATABASE_PASSWORD": "postgres",
        "DATABASE_HOST": "localhost",
        "DATABASE_PORT": "5432",
        "DEFAULT_USER": "user",
        "USING_JWT": "false",
        "CHROMA_PORT": "8000",
        "CHROMA_SSL": "false",
        "DISABLED_EXTENSIONS": "",
        "DISABLED_PROVIDERS": "",
        "REGISTRATION_DISABLED": "false",
        "AUTH_PROVIDER": "",
        "CREATE_AGENT_ON_REGISTER": "true",
        "CREATE_AGIXT_AGENT": "true",
    }
    default_value = default_values[var_name] if var_name in default_values else ""
    return os.getenv(var_name, default_value)


def get_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(text))
    return num_tokens


def get_default_agent_settings():
    if os.path.exists("default_agent.json"):
        with open("default_agent.json", "r") as f:
            agent_config = json.load(f)
            if "settings" in agent_config:
                return agent_config["settings"]
    if getenv("EZLOCALAI_API_KEY") == "":
        agent_settings = {
            "provider": "gpt4free",
            "mode": "prompt",
            "prompt_category": "Default",
            "prompt_name": "Chat",
            "embeddings_provider": "default",
            "tts_provider": "None",
            "transcription_provider": "default",
            "translation_provider": "default",
            "image_provider": "None",
            "vision_provider": "None",
            "AI_MODEL": "gpt-3.5-turbo",
            "AI_TEMPERATURE": "0.7",
            "AI_TOP_P": "1",
            "MAX_TOKENS": "4096",
            "helper_agent_name": "gpt4free",
            "analyze_user_input": True,
            "websearch": False,
            "websearch_depth": 2,
            "WEBSEARCH_TIMEOUT": 0,
            "WAIT_BETWEEN_REQUESTS": 1,
            "WAIT_AFTER_FAILURE": 3,
            "context_results": 10,
            "conversation_results": 6,
            "persona": "",
        }
    else:
        max_tokens = int(getenv("LLM_MAX_TOKENS"))
        if max_tokens == 0:
            max_tokens = 16384
        if max_tokens > 16384:
            context_results = 20
        else:
            context_results = 10
        if max_tokens > 32000:
            context_results = 50
        agent_settings = {
            "provider": "ezlocalai",
            "tts_provider": "ezlocalai",
            "transcription_provider": "ezlocalai",
            "translation_provider": "ezlocalai",
            "embeddings_provider": "default",
            "image_provider": "None",
            "vision_provider": "ezlocalai",
            "EZLOCALAI_API_KEY": getenv("EZLOCALAI_API_KEY"),
            "AI_MODEL": "ezlocalai",
            "EZLOCALAI_API_URI": getenv("EZLOCALAI_URI"),
            "TRANSCRIPTION_MODEL": "base",
            "MAX_TOKENS": int(getenv("LLM_MAX_TOKENS")),
            "AI_TEMPERATURE": 1.2,
            "AI_TOP_P": 0.95,
            "VOICE": "Morgan_Freeman",
            "mode": "prompt",
            "prompt_name": "Chat",
            "prompt_category": "Default",
            "helper_agent_name": "gpt4free",
            "analyze_user_input": True,
            "websearch": False,
            "websearch_depth": 2,
            "WEBSEARCH_TIMEOUT": 0,
            "WAIT_BETWEEN_REQUESTS": 1,
            "WAIT_AFTER_FAILURE": 3,
            "context_results": context_results,
            "conversation_results": 6,
            "persona": "",
        }
    return agent_settings


def get_default_agent():
    if os.path.exists("default_agent.json"):
        with open("default_agent.json", "r") as f:
            agent_config = json.load(f)
            agent_settings = get_default_agent_settings()
            agent_commands = (
                agent_config["commands"] if "commands" in agent_config else {}
            )
            training_urls = (
                agent_config["training_urls"] if "training_urls" in agent_config else []
            )
            return {
                "settings": agent_settings,
                "commands": agent_commands,
                "training_urls": training_urls,
            }
    return {
        "settings": get_default_agent_settings(),
        "commands": {},
        "training_urls": [],
    }


def get_agixt_training_urls():
    return [
        "https://josh-xt.github.io/AGiXT/",
        "https://josh-xt.github.io/AGiXT/1-Getting%20started/3-Examples.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/0-Core%20Concepts.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/01-Processes%20and%20Frameworks.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/02-Providers.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/03-Agents.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/04-Chat%20Completions.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/05-Extension%20Commands.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/06-Prompts.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/07-Chains.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/07-Conversations.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/09-Agent%20Training.html",
        "https://josh-xt.github.io/AGiXT/2-Concepts/10-Agent%20Interactions.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/0-ezLocalai.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/1-Anthropic%20Claude.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/2-Azure%20OpenAI.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/3-Google.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/4-GPT4Free.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/5-Hugging%20Face.html",
        "https://josh-xt.github.io/AGiXT/3-Providers/6-OpenAI.html",
        "https://josh-xt.github.io/AGiXT/4-Authentication/microsoft.html",
        "https://josh-xt.github.io/AGiXT/4-Authentication/google.html",
    ]


DEFAULT_USER = str(getenv("DEFAULT_USER")).lower()
DEFAULT_SETTINGS = get_default_agent_settings()
