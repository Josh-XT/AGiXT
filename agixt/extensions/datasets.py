import os
from Extensions import Extensions
import asyncio
import json


class agixt_actions(Extensions):
    def __init__(self, **kwargs):
        self.commands = {
            "Create Task Chain": self.create_task_chain,
            "Generate Extension from OpenAPI": self.generate_openapi_chain,
        }
        self.command_name = (
            kwargs["command_name"] if "command_name" in kwargs else "Smart Prompt"
        )
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_name = (
            kwargs["conversation_name"] if "conversation_name" in kwargs else ""
        )
        self.WORKING_DIRECTORY = os.path.join(os.getcwd(), "WORKSPACE")
        os.makedirs(self.WORKING_DIRECTORY, exist_ok=True)
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None

    # Convert LLM response of a list of either numbers like a numbered list, *'s, -'s to a list from the string response
    async def convert_llm_response_to_list(self, response):
        response = response.split("\n")
        response = [item.lstrip("0123456789.*- ") for item in response if item.lstrip()]
        response = [item for item in response if item]
        response = [item.lstrip("0123456789.*- ") for item in response]
        return response

    async def convert_memories_to_dataset(self):
        memories = await self.ApiClient.export_agent_memories(self.agent_name)
        tasks = []
        for memory in memories:
            task = asyncio.create_task(
                await self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Ask Questions",
                    prompt_args={
                        "memory": memory["text"],
                        "conversation_name": "AGiXT Terminal",
                    },
                )
            )
            tasks.append(task)
        responses = await asyncio.gather(*tasks)
        questions = []
        for response in responses:
            questions += await self.convert_llm_response_to_list(response)

        i = 0
        for question in questions:
            i += 1
            if i % 10 == 0:
                await asyncio.gather(*tasks)
                tasks = []
            task = asyncio.create_task(
                await self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Basic With Memory",
                    prompt_args={
                        "user_input": question,
                        "context_results": 10,
                        "conversation_name": f"{self.conversation_name} Dataset",
                        "persist_context_in_history": True,
                    },
                )
            )
            tasks.append(task)
        await asyncio.gather(*tasks)

        # Get conversation history of Dataset
        conversation_history = await self.ApiClient.get_conversation(
            agent_name=self.agent_name,
            conversation_name=f"{self.conversation_name} Dataset",
        )
        return conversation_history
