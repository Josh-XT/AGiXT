import os
import json
import tiktoken
from dotenv import load_dotenv

load_dotenv()


def getenv(var_name: str, default_value: str = "") -> str:
    default_values = {
        "AGIXT_URI": "http://localhost:7437",
        "APP_URI": "http://localhost:3437",
        "AGIXT_API_KEY": "None",
        "EZLOCALAI_URI": "http://localhost:8091/v1/",
        "EZLOCALAI_API_KEY": "",
        "AGENT_NAME": "AGiXT",
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
        "CREATE_AGENT_ON_REGISTER": "true",
        "CREATE_AGIXT_AGENT": "true",
        "SEED_DATA": "true",
        "GRAPHIQL": "true",
        "EZLOCALAI_VOICE": "DukeNukem",
        "TRAINING_URLS": "",
        "ENABLED_COMMANDS": "",
        "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
        "DEEPSEEK_MODEL": "deepseek-chat",
        "AZURE_MODEL": "gpt-4o",
        "GOOGLE_MODEL": "gemini-2.0-flash-exp",
        "OPENAI_MODEL": "chatgpt-4o-latest",
        "XAI_MODEL": "grok-beta",
        "EZLOCALAI_MAX_TOKENS": "16000",
        "DEEPSEEK_MAX_TOKENS": "60000",
        "AZURE_MAX_TOKENS": "100000",
        "XAI_MAX_TOKENS": "120000",
        "OPENAI_MAX_TOKENS": "128000",
        "ANTHROPIC_MAX_TOKENS": "140000",
        "GOOGLE_MAX_TOKENS": "1048000",
        "AZURE_API_KEY": "",
        "GOOGLE_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "XAI_API_KEY": "",
        "EZLOCALAI_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
        "AZURE_OPENAI_ENDPOINT": "",
    }
    if var_name == "MAGIC_LINK_URL":
        var_name = "APP_URI"
    if default_value != "":
        default_values[var_name] = default_value
    default_value = default_values[var_name] if var_name in default_values else ""
    return os.getenv(var_name, default_value)


def get_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(text))
    return num_tokens


def get_default_agent_settings():
    agent_settings = {
        "provider": "rotation",
        "vision_provider": "rotation",
        "tts_provider": ("ezlocalai" if getenv("EZLOCALAI_API_KEY") != "" else "None"),
        "transcription_provider": "default",
        "translation_provider": "default",
        "embeddings_provider": "default",
        "image_provider": "None",
        "ANTHROPIC_API_KEY": getenv("ANTHROPIC_API_KEY"),
        "ANTHROPIC_MODEL": getenv("ANTHROPIC_MODEL"),
        "AZURE_MODEL": getenv("AZURE_MODEL"),
        "AZURE_API_KEY": getenv("AZURE_API_KEY"),
        "AZURE_OPENAI_ENDPOINT": getenv("AZURE_OPENAI_ENDPOINT"),
        "AZURE_DEPLOYMENT_NAME": getenv("AZURE_MODEL"),
        "AZURE_TEMPERATURE": 0.7,
        "AZURE_TOP_P": 0.95,
        "DEEPSEEK_API_KEY": getenv("DEEPSEEK_API_KEY"),
        "DEEPSEEK_MODEL": getenv("DEEPSEEK_MODEL"),
        "GOOGLE_API_KEY": getenv("GOOGLE_API_KEY"),
        "GOOGLE_MODEL": getenv("GOOGLE_MODEL"),
        "GOOGLE_TEMPERATURE": 0.7,
        "GOOGLE_TOP_P": 0.95,
        "EZLOCALAI_API_KEY": getenv("EZLOCALAI_API_KEY"),
        "EZLOCALAI_API_URI": getenv("EZLOCALAI_API_URI", getenv("EZLOCALAI_URI")),
        "EZLOCALAI_VOICE": getenv("EZLOCALAI_VOICE"),
        "EZLOCALAI_TEMPERATURE": 1.33,
        "EZLOCALAI_TOP_P": 0.95,
        "OPENAI_API_KEY": getenv("OPENAI_API_KEY"),
        "OPENAI_MODEL": getenv("OPENAI_MODEL"),
        "XAI_API_KEY": getenv("XAI_API_KEY"),
        "XAI_MODEL": getenv("XAI_MODEL"),
        "EZLOCALAI_MAX_TOKENS": getenv("EZLOCALAI_MAX_TOKENS"),
        "DEEPSEEK_MAX_TOKENS": getenv("DEEPSEEK_MAX_TOKENS"),
        "AZURE_MAX_TOKENS": getenv("AZURE_MAX_TOKENS"),
        "XAI_MAX_TOKENS": getenv("XAI_MAX_TOKENS"),
        "OPENAI_MAX_TOKENS": getenv("OPENAI_MAX_TOKENS"),
        "ANTHROPIC_MAX_TOKENS": getenv("ANTHROPIC_MAX_TOKENS"),
        "GOOGLE_MAX_TOKENS": getenv("GOOGLE_MAX_TOKENS"),
        "SMARTEST_PROVIDER": "anthropic",
        "mode": "prompt",
        "prompt_name": "Think About It",
        "prompt_category": "Default",
        "analyze_user_input": False,
        "websearch": False,
        "websearch_depth": 2,
        "WEBSEARCH_TIMEOUT": 0,
        "persona": getenv("AGENT_PERSONA"),
        "tts": False,
    }
    for key in list(agent_settings.keys()):
        if agent_settings[key] == "":
            del agent_settings[key]
    return agent_settings


def get_default_agent_enabled_commands():
    enabled_commands = getenv("ENABLED_COMMANDS")
    if enabled_commands == "":
        return {}
    commands = {}
    if "," in enabled_commands:
        enabled_commands = enabled_commands.split(",")
    else:
        enabled_commands = [enabled_commands]
    for command in enabled_commands:
        commands[command] = True
    return commands


def get_default_training_urls():
    training_urls = getenv("TRAINING_URLS")
    if training_urls == "":
        return []
    if "," in training_urls:
        training_urls = training_urls.split(",")
    else:
        training_urls = [training_urls]
    return training_urls


def get_default_agent():
    return {
        "settings": get_default_agent_settings(),
        "commands": get_default_agent_enabled_commands(),
        "training_urls": get_default_training_urls(),
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


def get_output_url(path: str):
    agixt_uri = getenv("AGIXT_URI")
    new_path = path.split("/WORKSPACE/")[-1]
    return f"{agixt_uri}/{new_path}"


DEFAULT_USER = str(getenv("DEFAULT_USER")).lower()
DEFAULT_SETTINGS = get_default_agent_settings()
