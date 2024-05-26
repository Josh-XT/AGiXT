from DBConnection import User
from Interactions import Interactions
from ApiClient import get_api_client
from datetime import datetime
from Defaults import DEFAULT_SETTINGS


class AGiXT:
    def __init__(self, user: User, agent_name: str, api_key: str):
        self.user = user
        self.api_key = api_key
        self.agent_name = agent_name
        self.ApiClient = get_api_client(api_key)
        self.agent_interactions = Interactions(
            agent_name=self.agent_name, user=self.user.email, ApiClient=self.ApiClient
        )
        self.agent = self.agent_interactions.agent
        self.agent_settings = (
            self.agent.AGENT_CONFIG["settings"]
            if "settings" in self.agent.AGENT_CONFIG
            else DEFAULT_SETTINGS
        )

    async def inference(
        self,
        user_input: str = "",
        context_results: int = 5,
        shots: int = 1,
        conversation_name: str = "",
        browse_links: bool = False,
        images: list = [],
    ):
        if conversation_name == "":
            conversation_name = datetime.now().strftime("%Y-%m-%d")
        return await self.agent_interactions.run(
            user_input=user_input,
            context_results=context_results,
            shots=shots,
            conversation_name=conversation_name,
            browse_links=browse_links,
            images=images,
        )
