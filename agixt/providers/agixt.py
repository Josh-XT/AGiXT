from ApiClient import ApiClient


# This will create a hive agent that will create memories for itself and each agent in the rotation.
# If one agent fails, it will move on to the next agent in the rotation.
class AgixtProvider:
    def __init__(
        self,
        agents: list = [],
        MAX_TOKENS: int = 16000,
        **kwargs,
    ):
        self.requirements = ["agixtsdk"]
        self.MAX_TOKENS = int(MAX_TOKENS) if int(MAX_TOKENS) != 0 else 16000
        self.agents = ApiClient.get_agents() if agents == [] else agents

    async def instruct(self, prompt, tokens: int = 0):
        for agent in self.agents:
            try:
                return ApiClient.prompt_agent(
                    agent_name=agent,
                    prompt="Custom Input",
                    prompt_args={"user_input": prompt},
                )
            except Exception as e:
                print(f"[AGiXT] {agent} failed. Error: {e}. Moving on to next agent.")
                continue
        return "No agents available"
