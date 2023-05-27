import os

OPENAI_API_KEY = os.getenv("API_KEY")


cfg = {
    # AGENT settings
    "agent_name": "test_agent",
    "agent_settings_gpt4free": {"provider": "gpt4free"},
    "agent_settings_openai": {
        "provider": "openai",
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "AI_MODEL": "gpt-3.5-turbo",
        "AI_TEMPERATURE": "0.7",
        "MAX_TOKENS": "4000",
        "embedder": "openai",
    },
    "agent_commands": {
        "Get Response": True,
        "Google Search": True,
        "Is Valid URL": True,
        "Sanitize URL": True,
        "Scrape Links": True,
        "Scrape Links with Playwright": True,
        "Scrape Text": True,
        "Scrape Text with Playwright": True,
        #                        'Scrape Text with Selenium': True,
        "Use The Search Engine": True,
    },
    "shots": 3,
    "message-1": "Write a short text about AI suitable for a tweet.",
    "message-2": "Hi! Can you write me a short story about the sun and the clouds?",
    "message-3": "What is the capital of france?",
}
