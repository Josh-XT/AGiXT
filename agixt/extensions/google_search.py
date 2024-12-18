from Extensions import Extensions
from agixtsdk import AGiXTSDK


class google_search(Extensions):
    """
    The Google Search extension for AGiXT enables you to search Google using the Google Search API.
    """

    def __init__(
        self,
        GOOGLE_API_KEY: str = "",
        GOOGLE_SEARCH_ENGINE_ID: str = "",
        **kwargs,
    ):
        self.commands = {
            "Google Search": self.google_search,
        }
        self.GOOGLE_API_KEY = GOOGLE_API_KEY
        self.GOOGLE_SEARCH_ENGINE_ID = GOOGLE_SEARCH_ENGINE_ID
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else AGiXTSDK()
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )

    async def google_search(self, user_query: str, websearch_depth: int = 2):
        return self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": user_query,
                "websearch": True,
                "websearch_depth": websearch_depth,
                "websearch_query": user_query,
                "conversation_name": self.conversation_name,
                "log_user_input": False,
                "log_output": False,
                "tts": False,
                "analyze_user_input": False,
                "disable_commands": True,
            },
        )
