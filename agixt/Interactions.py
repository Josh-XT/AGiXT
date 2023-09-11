import re
import regex
import json
import time
import logging
import tiktoken
from datetime import datetime
from readers.website import WebsiteReader
from ApiClient import ApiClient, DB_CONNECTED

if DB_CONNECTED:
    from db.Agent import Agent
    from db.Prompts import Prompts
    from db.Chain import Chain
    from db.History import log_interaction, get_conversation
else:
    from fb.Agent import Agent
    from fb.Prompts import Prompts
    from fb.Chain import Chain
    from fb.History import log_interaction, get_conversation

from Websearch import Websearch
from Extensions import Extensions

chain = Chain()
cp = Prompts()


def get_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(text))
    return num_tokens


class Interactions:
    def __init__(self, agent_name: str = "", collection_number: int = 0):
        if agent_name != "":
            self.agent_name = agent_name
            self.agent = Agent(self.agent_name)
            self.agent_commands = self.agent.get_commands_string()
            self.websearch = Websearch(
                agent_name=self.agent_name,
                searxng_instance_url=self.agent.AGENT_CONFIG["settings"][
                    "SEARXNG_INSTANCE_URL"
                ]
                if "SEARXNG_INSTANCE_URL" in self.agent.AGENT_CONFIG["settings"]
                else "",
            )
        else:
            self.agent_name = ""
            self.agent = None
            self.agent_commands = ""

        self.agent_memory = WebsiteReader(
            agent_name=self.agent_name,
            agent_config=self.agent.AGENT_CONFIG,
            collection_number=int(collection_number),
        )
        self.stop_running_event = None
        self.browsed_links = []
        self.failures = 0

    def custom_format(self, string, **kwargs):
        if isinstance(string, list):
            string = "".join(str(x) for x in string)

        def replace(match):
            key = match.group(1)
            value = kwargs.get(key, match.group(0))
            if isinstance(value, list):
                return "".join(str(x) for x in value)
            else:
                return str(value)

        pattern = r"(?<!{){([^{}\n]+)}(?!})"
        result = re.sub(pattern, replace, string)
        return result

    async def format_prompt(
        self,
        user_input: str = "",
        top_results: int = 5,
        prompt="",
        prompt_category="Default",
        chain_name="",
        step_number=0,
        conversation_name="",
        websearch: bool = False,
        **kwargs,
    ):
        if "user_input" in kwargs and user_input == "":
            user_input = kwargs["user_input"]
        prompt_name = prompt if prompt != "" else "Custom Input"
        try:
            prompt = cp.get_prompt(
                prompt_name=prompt_name,
                prompt_category=self.agent.AGENT_CONFIG["settings"]["AI_MODEL"]
                if prompt_category == "Default"
                else prompt_category,
            )
        except:
            prompt = prompt_name
        logging.info(f"CONTEXT RESULTS: {top_results}")
        if top_results == 0:
            context = []
        else:
            if user_input:
                min_relevance_score = 0.0
                if "min_relevance_score" in kwargs:
                    try:
                        min_relevance_score = float(kwargs["min_relevance_score"])
                    except:
                        min_relevance_score = 0.0
                context = await self.agent_memory.get_memories(
                    user_input=user_input,
                    limit=top_results,
                    min_relevance_score=min_relevance_score,
                )
                if websearch:
                    context += await WebsiteReader(
                        agent_name=self.agent_name,
                        agent_config=self.agent.AGENT_CONFIG,
                        collection_number=1,
                    ).get_memories(
                        user_input=user_input,
                        limit=top_results,
                        min_relevance_score=min_relevance_score,
                    )
                if "inject_memories_from_collection_number" in kwargs:
                    if int(kwargs["inject_memories_from_collection_number"]) > 0:
                        context += await WebsiteReader(
                            agent_name=self.agent_name,
                            agent_config=self.agent.AGENT_CONFIG,
                            collection_number=int(
                                kwargs["inject_memories_from_collection_number"]
                            ),
                        ).get_memories(
                            user_input=user_input,
                            limit=top_results,
                            min_relevance_score=min_relevance_score,
                        )
            else:
                context = []
        if "context" in kwargs:
            context += [kwargs["context"]]
            del kwargs["context"]
        if context != [] and context != "":
            context = "\n".join(context)
            context = f"The user's input causes you remember these things:\n{context}\n"
        else:
            context = ""

        command_list = self.agent.get_commands_string()
        if chain_name != "":
            try:
                for arg, value in kwargs.items():
                    if "{STEP" in value:
                        # get the response from the step number
                        step_response = chain.get_step_response(
                            chain_name=chain_name, step_number=step_number
                        )
                        # replace the {STEPx} with the response
                        value = value.replace(f"{{STEP{step_number}}}", step_response)
                        kwargs[arg] = value
            except:
                logging.info("No args to replace.")
            if "{STEP" in prompt:
                step_response = chain.get_step_response(
                    chain_name=chain_name, step_number=step_number
                )
                prompt = prompt.replace(f"{{STEP{step_number}}}", step_response)
            if "{STEP" in user_input:
                step_response = chain.get_step_response(
                    chain_name=chain_name, step_number=step_number
                )
                user_input = user_input.replace(f"{{STEP{step_number}}}", step_response)
        try:
            working_directory = self.agent.AGENT_CONFIG["settings"]["WORKING_DIRECTORY"]
        except:
            working_directory = "./WORKSPACE"
        if "helper_agent_name" not in kwargs:
            if "helper_agent_name" in self.agent.AGENT_CONFIG["settings"]:
                helper_agent_name = self.agent.AGENT_CONFIG["settings"][
                    "helper_agent_name"
                ]
            else:
                helper_agent_name = self.agent_name
        if "conversation_name" in kwargs:
            conversation_name = kwargs["conversation_name"]
        if conversation_name == "":
            conversation_name = f"{str(datetime.now())} Conversation"
        conversation = get_conversation(
            agent_name=self.agent_name,
            conversation_name=conversation_name,
        )
        if "conversation_results" in kwargs:
            conversation_results = int(kwargs["conversation_results"])
        else:
            conversation_results = int(top_results) if top_results > 0 else 5
        conversation_history = ""
        if "interactions" in conversation and conversation["interactions"] != []:
            x = 1
            for interaction in conversation["interactions"]:
                if conversation_results > x:
                    timestamp = (
                        interaction["timestamp"] if "timestamp" in interaction else ""
                    )
                    role = interaction["role"] if "role" in interaction else ""
                    message = interaction["message"] if "message" in interaction else ""
                    conversation_history += f"{timestamp} {role}: {message} \n "
                    x += 1
                else:
                    break
        if "conversation_history" in kwargs:
            del kwargs["conversation_history"]

        verbose_commands = "**You have commands available to use if they would be useful to complete a user's task.**\n```json\n{\n"

        for command in self.agent.available_commands:
            verbose_commands += f'    "{command["friendly_name"]}": {{\n'
            for arg in command["args"]:
                verbose_commands += f'        "{arg}": "Your hallucinated input",\n'
            verbose_commands += "    },\n"

        verbose_commands += "}\n```"
        verbose_commands += """
**RESPOND IN THE FOLLOWING JSON FORMAT ONLY! If there are no commands worth executing to assist the user, simply make the commands section an empty object like {}.**
```JSON
{
    "response": "Your response to the task.",
    "commands": {
        "command_name": {
            "arg1": "val1",
            "arg2": "val2"
        },
        "command_name2": {
            "arg1": "val1",
            "arg2": "val2",
            "argN": "valN"
        }
    }
}
        """
        formatted_prompt = self.custom_format(
            string=prompt,
            user_input=user_input,
            agent_name=self.agent_name,
            COMMANDS=verbose_commands,
            context=context,
            command_list=command_list,
            date=datetime.now().strftime("%B %d, %Y %I:%M %p"),
            working_directory=working_directory,
            helper_agent_name=helper_agent_name,
            conversation_history=conversation_history,
            **kwargs,
        )

        tokens = get_tokens(formatted_prompt)
        logging.info(f"FORMATTED PROMPT: {formatted_prompt}")
        return formatted_prompt, prompt, tokens

    async def run(
        self,
        user_input: str = "",
        prompt: str = "",
        context_results: int = 5,
        websearch: bool = False,
        websearch_depth: int = 3,
        chain_name: str = "",
        step_number: int = 0,
        shots: int = 1,
        disable_memory: bool = False,
        conversation_name: str = "",
        browse_links: bool = False,
        prompt_category: str = "Default",
        **kwargs,
    ):
        shots = int(shots)
        if "prompt_category" in kwargs:
            prompt_category = kwargs["prompt_category"]
        disable_memory = True if str(disable_memory).lower() == "true" else False
        browse_links = True if str(browse_links).lower() == "true" else False
        if "conversation_name" in kwargs:
            conversation_name = kwargs["conversation_name"]
        if conversation_name == "":
            conversation_name = f"{str(datetime.now())} Conversation"
        if "WEBSEARCH_TIMEOUT" in self.agent.PROVIDER_SETTINGS:
            try:
                websearch_timeout = int(
                    self.agent.PROVIDER_SETTINGS["WEBSEARCH_TIMEOUT"]
                )
            except:
                websearch_timeout = 0
        else:
            websearch_timeout = 0
        if browse_links != False:
            links = re.findall(r"(?P<url>https?://[^\s]+)", user_input)
            if links is not None and len(links) > 0:
                for link in links:
                    if link not in self.websearch.browsed_links:
                        logging.info(f"Browsing link: {link}")
                        self.websearch.browsed_links.append(link)
                        (
                            text_content,
                            link_list,
                        ) = await self.agent_memory.write_website_to_memory(url=link)
                        if int(websearch_depth) > 0:
                            if link_list is not None and len(link_list) > 0:
                                i = 0
                                for sublink in link_list:
                                    if sublink[1] not in self.websearch.browsed_links:
                                        logging.info(f"Browsing link: {sublink[1]}")
                                        if i <= websearch_depth:
                                            (
                                                text_content,
                                                link_list,
                                            ) = await self.agent_memory.write_website_to_memory(
                                                url=sublink[1]
                                            )
                                            i = i + 1
        if websearch:
            if user_input == "":
                if "primary_objective" in kwargs and "task" in kwargs:
                    search_string = f"Primary Objective: {kwargs['primary_objective']}\n\nTask: {kwargs['task']}"
                else:
                    search_string = ""
            else:
                search_string = user_input
            if search_string != "":
                await self.websearch.websearch_agent(
                    user_input=search_string,
                    websearch_depth=websearch_depth,
                    websearch_timeout=websearch_timeout,
                )
        formatted_prompt, unformatted_prompt, tokens = await self.format_prompt(
            user_input=user_input,
            top_results=int(context_results),
            prompt=prompt,
            prompt_category=prompt_category,
            chain_name=chain_name,
            step_number=step_number,
            conversation_name=conversation_name,
            websearch=websearch,
            **kwargs,
        )
        log_interaction(
            agent_name=self.agent_name,
            conversation_name=conversation_name,
            role="USER",
            message=user_input if user_input != "" else formatted_prompt,
        )
        try:
            self.response = await self.agent.instruct(formatted_prompt, tokens=tokens)
        except Exception as e:
            logging.info(f"Error: {e}")
            logging.info(f"PROMPT CONTENT: {formatted_prompt}")
            logging.info(f"TOKENS: {tokens}")
            self.failures += 1
            if self.failures == 5:
                self.failures == 0
                logging.info("Failed to get a response 5 times in a row.")
                return None
            logging.info(f"Retrying in 10 seconds...")
            time.sleep(10)
            if context_results > 0:
                context_results = context_results - 1
            self.response = ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name=prompt,
                prompt_args={
                    "chain_name": chain_name,
                    "step_number": step_number,
                    "shots": shots,
                    "disable_memory": disable_memory,
                    "user_input": user_input,
                    "context_results": context_results,
                    "conversation_name": conversation_name,
                    **kwargs,
                },
            )

        # Handle commands if the prompt contains the {COMMANDS} placeholder
        # We handle command injection that DOESN'T allow command execution by using {command_list} in the prompt
        if "{COMMANDS}" in unformatted_prompt:
            execution_response = await self.execution_agent(
                execution_response=self.response,
                user_input=user_input,
                context_results=context_results,
                disable_memory=disable_memory,
                conversation_name=conversation_name,
                **kwargs,
            )
            if "AUTONOMOUS_EXECUTION" in self.agent.AGENT_CONFIG["settings"]:
                autonomous = (
                    True
                    if self.agent.AGENT_CONFIG["settings"]["AUTONOMOUS_EXECUTION"]
                    == True
                    else False
                )
            else:
                autonomous = False
            if autonomous == True:
                try:
                    self.response = json.loads(self.response)
                    if "response" in self.response:
                        self.response = self.response["response"]
                except:
                    pass
            else:
                self.response = f"{self.response}\n\n{execution_response}"
        logging.info(f"Response: {self.response}")
        if self.response != "" and self.response != None:
            if disable_memory != True:
                try:
                    await self.agent_memory.write_text_to_memory(
                        user_input=user_input,
                        text=self.response,
                        external_source="user input",
                    )
                except:
                    pass
            log_interaction(
                agent_name=self.agent_name,
                conversation_name=conversation_name,
                role=self.agent_name,
                message=self.response,
            )
        if shots > 1:
            responses = [self.response]
            for shot in range(shots - 1):
                shot_response = ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name=prompt,
                    prompt_args={
                        "chain_name": chain_name,
                        "step_number": step_number,
                        "user_input": user_input,
                        "context_results": context_results,
                        "conversation_name": conversation_name,
                        "disable_memory": disable_memory,
                        **kwargs,
                    },
                )
                time.sleep(1)
                responses.append(shot_response)
            return "\n".join(
                [
                    f"Response {shot + 1}:\n{response}"
                    for shot, response in enumerate(responses)
                ]
            )
        return self.response

    # Worker Sub-Agents
    async def validation_agent(
        self,
        user_input,
        execution_response,
        context_results,
        disable_memory,
        conversation_name,
        **kwargs,
    ):
        try:
            pattern = regex.compile(r"\{(?:[^{}]|(?R))*\}")
            cleaned_json = pattern.findall(execution_response)
            if len(cleaned_json) == 0:
                return {}
            if isinstance(cleaned_json, list):
                cleaned_json = cleaned_json[0]
            response = json.loads(cleaned_json)
            return response
        except:
            logging.info("INVALID JSON RESPONSE")
            logging.info(execution_response)
            logging.info("... Trying again.")
            if context_results != 0:
                context_results = context_results - 1
            else:
                context_results = 0
            execution_response = ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="JSONFormatter",
                prompt_args={
                    "user_input": user_input,
                    "context_results": context_results,
                    "conversation_name": conversation_name,
                    "disable_memory": disable_memory,
                    **kwargs,
                },
            )
            return await self.validation_agent(
                user_input=user_input,
                execution_response=execution_response,
                context_results=context_results,
                disable_memory=disable_memory,
                conversation_name=conversation_name,
                **kwargs,
            )

    def create_command_suggestion_chain(self, agent_name, command_name, command_args):
        chains = ApiClient.get_chains()
        chain_name = f"{agent_name} Command Suggestions"
        if chain_name in chains:
            step = (
                int(ApiClient.get_chain(chain_name=chain_name)["steps"][-1]["step"]) + 1
            )
        else:
            ApiClient.add_chain(chain_name=chain_name)
            step = 1
        ApiClient.add_step(
            chain_name=chain_name,
            agent_name=agent_name,
            step_number=step,
            prompt_type="Command",
            prompt={
                "command_name": command_name,
                **command_args,
            },
        )
        return f"The command has been added to a chain called '{agent_name} Command Suggestions' for you to review and execute manually."

    async def execution_agent(
        self,
        execution_response,
        user_input,
        context_results,
        disable_memory,
        conversation_name,
        **kwargs,
    ):
        validated_response = await self.validation_agent(
            user_input=user_input,
            execution_response=execution_response,
            context_results=context_results,
            disable_memory=disable_memory,
            conversation_name=conversation_name,
            **kwargs,
        )
        messages = ""
        if "commands" in validated_response:
            for command_name, command_args in validated_response["commands"].items():
                # Search for the command in the available_commands list, and if found, use the command's name attribute for execution
                if command_name is not None:
                    for available_command in self.agent.available_commands:
                        if command_name == available_command["friendly_name"]:
                            # Check if the command is a valid command in the self.avent.available_commands list
                            try:
                                if bool(self.agent.AUTONOMOUS_EXECUTION) == True:
                                    ext = Extensions(
                                        agent_name=self.agent_name,
                                        agent_config=self.agent.AGENT_CONFIG,
                                        conversation_name=conversation_name,
                                    )
                                    command_output = await ext.execute_command(
                                        command_name=command_name,
                                        command_args=command_args,
                                    )
                                    formatted_output = (
                                        f"```\n{command_output}\n```"
                                        if "#GENERATED_IMAGE" not in command_output
                                        and "#GENERATED_AUDIO" not in command_output
                                        else command_output
                                    )
                                    message = f"**Executed Command:** `{command_name}` with the following parameters:\n```json\n{json.dumps(command_args, indent=4)}\n```\n\n**Command Output:**\n{formatted_output}"
                                else:
                                    command_output = (
                                        self.create_command_suggestion_chain(
                                            agent_name=self.agent_name,
                                            command_name=command_name,
                                            command_args=command_args,
                                        )
                                    )
                                    message = (
                                        f"**Agent execution chain updated for command `{command_name}` with the following parameters:** \n```json\n{json.dumps(command_args, indent=4)}\n```\n",
                                    )
                            except Exception as e:
                                logging.info("Command validation failed, retrying...")
                                validate_command = ApiClient.prompt_agent(
                                    agent_name=self.agent_name,
                                    prompt_name="ValidationFailed",
                                    prompt_args={
                                        "command_name": command_name,
                                        "command_args": command_args,
                                        "command_output": e,
                                        "user_input": user_input,
                                        "context_results": context_results,
                                        "conversation_name": conversation_name,
                                        "disable_memory": disable_memory,
                                        **kwargs,
                                    },
                                )
                                message = await self.execution_agent(
                                    execution_response=validate_command,
                                    user_input=user_input,
                                    context_results=context_results,
                                    disable_memory=disable_memory,
                                    conversation_name=conversation_name,
                                    **kwargs,
                                )
                            messages += f"\n{message}\n\n"
        return messages
