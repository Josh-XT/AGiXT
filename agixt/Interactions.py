import os
import re
import regex
import json
import time
import logging
import tiktoken
from datetime import datetime
from readers.website import WebsiteReader
from readers.file import FileReader
from Websearch import Websearch
from Extensions import Extensions
from ApiClient import (
    ApiClient,
    Agent,
    Prompts,
    Chain,
    log_interaction,
    get_conversation,
)


def get_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(text))
    return num_tokens


class Interactions:
    def __init__(self, agent_name: str = "", collection_number: int = 0, user="USER"):
        if agent_name != "":
            self.agent_name = agent_name
            self.agent = Agent(self.agent_name, user=user)
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
        self.user = user
        self.chain = Chain(user=user)
        self.cp = Prompts(user=user)

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
            prompt = self.cp.get_prompt(
                prompt_name=prompt_name,
                prompt_category=self.agent.AGENT_CONFIG["settings"]["AI_MODEL"]
                if prompt_category == "Default"
                else prompt_category,
            )
            prompt_args = self.cp.get_prompt_args(prompt_text=prompt)
        except:
            prompt = prompt_name
            prompt_args = []
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
                positive_feedback = await WebsiteReader(
                    agent_name=self.agent_name,
                    agent_config=self.agent.AGENT_CONFIG,
                    collection_number=2,
                ).get_memories(
                    user_input=user_input,
                    limit=3,
                    min_relevance_score=0.7,
                )
                negative_feedback = await WebsiteReader(
                    agent_name=self.agent_name,
                    agent_config=self.agent.AGENT_CONFIG,
                    collection_number=3,
                ).get_memories(
                    user_input=user_input,
                    limit=3,
                    min_relevance_score=0.7,
                )
                if positive_feedback or negative_feedback:
                    context += f"The users input makes you to remember some feedback from previous interactions:\n"
                    if positive_feedback:
                        context += f"Positive Feedback:\n{positive_feedback}\n"
                    if negative_feedback:
                        context += f"Negative Feedback:\n{negative_feedback}\n"
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
                        step_response = self.chain.get_step_response(
                            chain_name=chain_name, step_number=step_number
                        )
                        # replace the {STEPx} with the response
                        value = value.replace(f"{{STEP{step_number}}}", step_response)
                        kwargs[arg] = value
            except:
                logging.info("No args to replace.")
            if "{STEP" in prompt:
                step_response = self.chain.get_step_response(
                    chain_name=chain_name, step_number=step_number
                )
                prompt = prompt.replace(f"{{STEP{step_number}}}", step_response)
            if "{STEP" in user_input:
                step_response = self.chain.get_step_response(
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
        persona = ""
        if "persona" in prompt_args:
            if "PERSONA" in self.agent.AGENT_CONFIG["settings"]:
                persona = self.agent.AGENT_CONFIG["settings"]["PERSONA"]
        if persona != "":
            persona = f"Your persona is: {persona}\n\n"
        verbose_commands = "**You have commands available to use if they would be useful to provide a better user experience.**\n```json\n{\n"
        for command in self.agent.available_commands:
            verbose_commands += f'    "{command["friendly_name"]}": {{\n'
            for arg in command["args"]:
                verbose_commands += f'        "{arg}": "Your hallucinated input",\n'
            verbose_commands += "    },\n"
        verbose_commands += "}\n```"
        verbose_commands = '**To execute a command, use the example below, it will be replaced with the commands output for the user. You can execute a command anywhere in your response and the commands will be executed in the order you use them.**\n#execute_command("Name of Command", {"arg1": "val1", "arg2": "val2"})'
        if prompt_name == "Chat with Commands" and command_list == "":
            prompt_name = "Chat"
        file_contents = ""
        if "import_files" in prompt_args:
            file_reader = FileReader(
                agent_name=self.agent_name,
                agent_config=self.agent.AGENT_CONFIG,
                collection=4,
            )
            # import_files should be formatted like [{"file_name": "file_content"}]
            files = []
            if "import_files" in kwargs:
                if kwargs["import_files"] != "":
                    try:
                        files = json.loads(kwargs["import_files"])
                    except:
                        files = []
            all_files_content = ""
            file_list = []
            for file in files:
                file_name = file["file_name"]
                file_list.append(file_name)
                file_name = regex.sub(r"(\[.*?\])", "", file_name)
                file_path = os.path.normpath(os.getcwd(), working_directory, file_name)
                if not file_path.startswith(os.getcwd()):
                    pass
                if not os.path.exists(file_path):
                    # Create it with the content if it doesn't exist.
                    with open(file_path, "w") as f:
                        f.write(file["file_content"])
                    file_content = file["file_content"]
                else:
                    with open(file_path, "r") as f:
                        file_content = f.read()
                    file_contents += f"\n`{file_path}` content:\n{file_content}\n\n"
                try:
                    await file_reader.write_file_to_memory(
                        file_path=file_path,
                    )
                except:
                    pass
                if file_name != "" and file_content != "":
                    all_files_content += file_content
            if files != []:
                the_files = (
                    f"these files: {', '.join(file_list)}."
                    if len(file_list) > 1
                    else f"the file {file_list[0]}."
                )
                log_interaction(
                    agent_name=self.agent_name,
                    conversation_name=conversation_name,
                    role=self.agent_name,
                    message=f"I have read the file contents of {the_files}.",
                    user=self.user,
                )
            else:
                the_files = "files."
            tokens_used = get_tokens(
                f"{prompt}{user_input}{all_files_content}{context}"
            )
            if tokens_used > int(self.agent.MAX_TOKENS) or files == []:
                fragmented_content = await file_reader.get_memories(
                    user_input=f"{user_input} {file_list}",
                    min_relevance_score=0.3,
                    limit=top_results if top_results > 0 else 5,
                )
                if fragmented_content != "":
                    file_contents = f"Here is some potentially relevant information from {the_files}\n{fragmented_content}\n\n"
        skip_args = [
            "user_input",
            "agent_name",
            "COMMANDS",
            "context",
            "command_list",
            "date",
            "working_directory",
            "helper_agent_name",
            "conversation_history",
            "persona",
            "import_files",
        ]
        args = kwargs.copy()
        for arg in kwargs:
            if arg in skip_args:
                del args[arg]
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
            persona=persona,
            import_files=file_contents,
            **args,
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
            user=self.user,
        )
        try:
            self.response = await self.agent.instruct(formatted_prompt, tokens=tokens)
        except Exception as e:
            # Log the error with the full traceback for the provider
            error = ""
            for err in e:
                error += f"{err.args}\n{err.name}\n{err.msg}\n"
            logging.error(f"{self.agent.PROVIDER} Error: {error}")
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
            return ApiClient.prompt_agent(
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
                    "prompt_category": prompt_category,
                    **kwargs,
                },
            )
        # Handle commands if the prompt contains the {COMMANDS} placeholder
        # We handle command injection that DOESN'T allow command execution by using {command_list} in the prompt
        if "{COMMANDS}" in unformatted_prompt:
            await self.execution_agent(conversation_name=conversation_name)
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
                user=self.user,
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
                        "prompt_category": prompt_category,
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
        return f"**The command has been added to a chain called '{agent_name} Command Suggestions' for you to review and execute manually.**"

    async def execution_agent(self, conversation_name):
        commands_to_execute = re.findall(r"#execute_command\((.*?)\)", self.response)
        if commands_to_execute:
            reformatted_response = self.response
            if len(commands_to_execute) > 0:
                for command in commands_to_execute:
                    command_name = command.split(",")[0]
                    if command_name:
                        if len(command.split(",")[1:]) > 0:
                            try:
                                command_args = json.loads(
                                    '{"command_args": '
                                    + ",".join(command.split(",")[1:])
                                    + "}"
                                )
                            except:
                                command_args = {}
                        for available_command in self.agent.available_commands:
                            if command_name == available_command["friendly_name"]:
                                # Check if the command is a valid command in the self.agent.available_commands list
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
                                        log_interaction(
                                            agent_name=self.agent_name,
                                            conversation_name=f"{self.agent_name} Command Execution Log",
                                            role=self.agent_name,
                                            message=message,
                                            user=self.user,
                                        )
                                    else:
                                        command_output = (
                                            self.create_command_suggestion_chain(
                                                agent_name=self.agent_name,
                                                command_name=command_name,
                                                command_args=command_args,
                                            )
                                        )
                                except Exception as e:
                                    logging.error(
                                        f"Error: {self.agent_name} failed to execute command `{command_name}`. {e}"
                                    )
                                    command_output = f"**Failed to execute command `{command_name}` with args `{command_args}`. Please try again.**"
                                reformatted_response = reformatted_response.replace(
                                    f"#execute_command({command_name}, {command_args})",
                                    command_output,
                                )
                if reformatted_response != self.response:
                    self.response = reformatted_response
