import os
import re
import regex
import json
import time
import logging
import base64
import uuid
import asyncio
from datetime import datetime
from readers.file import FileReader
from Websearch import Websearch
from Extensions import Extensions
from Memories import extract_keywords
from ApiClient import (
    Agent,
    Prompts,
    Chain,
    Conversations,
    AGIXT_URI,
)
from Globals import getenv, DEFAULT_USER, get_tokens

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


class Interactions:
    def __init__(
        self,
        agent_name: str = "",
        user=DEFAULT_USER,
        ApiClient=None,
    ):
        self.ApiClient = ApiClient
        self.user = user
        self.uri = getenv("AGIXT_URI")
        if agent_name != "":
            self.agent_name = agent_name
            self.agent = Agent(self.agent_name, user=user, ApiClient=self.ApiClient)
            self.agent_commands = self.agent.get_commands_string()
            self.websearch = Websearch(
                collection_number="1",
                agent=self.agent,
                user=self.user,
                ApiClient=self.ApiClient,
            )
            self.agent_memory = FileReader(
                agent_name=self.agent_name,
                agent_config=self.agent.AGENT_CONFIG,
                collection_number="0",
                ApiClient=self.ApiClient,
                user=self.user,
            )
            self.positive_feedback_memories = FileReader(
                agent_name=self.agent_name,
                agent_config=self.agent.AGENT_CONFIG,
                collection_number="2",
                ApiClient=self.ApiClient,
                user=self.user,
            )
            self.negative_feedback_memories = FileReader(
                agent_name=self.agent_name,
                agent_config=self.agent.AGENT_CONFIG,
                collection_number="3",
                ApiClient=self.ApiClient,
                user=self.user,
            )
            self.github_memories = FileReader(
                agent_name=self.agent_name,
                agent_config=self.agent.AGENT_CONFIG,
                collection_number="7",
                user=self.user,
                ApiClient=self.ApiClient,
            )
            self.outputs = f"{self.uri}/outputs/{self.agent.agent_id}"
        else:
            self.agent_name = ""
            self.agent = None
            self.agent_commands = ""
            self.websearch = None
            self.agent_memory = None
            self.positive_feedback_memories = None
            self.negative_feedback_memories = None
            self.github_memories = None
            self.outputs = f"{self.uri}/outputs"
        self.response = ""
        self.failures = 0
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
        conversation_name="",
        vision_response: str = "",
        searching: bool = False,
        **kwargs,
    ):
        if "user_input" in kwargs and user_input == "":
            user_input = kwargs["user_input"]
        prompt_name = prompt if prompt != "" else "Custom Input"
        prompt_category = (
            "Default" if "prompt_category" not in kwargs else kwargs["prompt_category"]
        )
        try:
            prompt = self.cp.get_prompt(
                prompt_name=prompt_name, prompt_category=prompt_category
            )
            prompt_args = self.cp.get_prompt_args(prompt_text=prompt)
        except Exception as e:
            logging.error(
                f"Error: {self.agent_name} failed to get prompt {prompt_name} from prompt category {prompt_category}. {e}"
            )
            prompt = prompt_name
            prompt_args = []
        if "conversation_name" in kwargs:
            conversation_name = kwargs["conversation_name"]
        if conversation_name == "":
            conversation_name = "-"
        c = Conversations(conversation_name=conversation_name, user=self.user)
        conversation = c.get_conversation()
        if top_results == 0:
            context = []
        else:
            if user_input:
                if self.websearch == None or self.websearch.collection_number == "1":
                    conversation_id = c.get_conversation_id()
                    self.websearch = Websearch(
                        collection_number=str(conversation_id),
                        agent=self.agent,
                        user=self.user,
                        ApiClient=self.ApiClient,
                    )
                min_relevance_score = 0.3
                if "min_relevance_score" in kwargs:
                    try:
                        min_relevance_score = float(kwargs["min_relevance_score"])
                    except:
                        min_relevance_score = 0.3
                context = await self.agent_memory.get_memories(
                    user_input=user_input,
                    limit=top_results,
                    min_relevance_score=min_relevance_score,
                )
                context += await self.websearch.agent_memory.get_memories(
                    user_input=user_input,
                    limit=top_results,
                    min_relevance_score=min_relevance_score,
                )
                context += await self.github_memories.get_memories(
                    user_input=user_input,
                    limit=top_results,
                    min_relevance_score=min_relevance_score,
                )
                positive_feedback = await self.positive_feedback_memories.get_memories(
                    user_input=user_input,
                    limit=3,
                    min_relevance_score=0.7,
                )
                negative_feedback = await self.negative_feedback_memories.get_memories(
                    user_input=user_input,
                    limit=3,
                    min_relevance_score=0.7,
                )
                if positive_feedback or negative_feedback:
                    context.append(
                        f"The users input makes you to remember some feedback from previous interactions:\n"
                    )
                    if positive_feedback:
                        joined_feedback = "\n".join(positive_feedback)
                        context.append(f"Positive Feedback:\n{joined_feedback}\n")
                    if negative_feedback:
                        joined_feedback = "\n".join(negative_feedback)
                        context.append(f"Negative Feedback:\n{joined_feedback}\n")
                if "inject_memories_from_collection_number" in kwargs:
                    collection_id = kwargs["inject_memories_from_collection_number"]
                    if collection_id not in ["0", "1", "2", "3", "4", "5", "6", "7"]:
                        context += await FileReader(
                            agent_name=self.agent_name,
                            agent_config=self.agent.AGENT_CONFIG,
                            collection_number=collection_id,
                            ApiClient=self.ApiClient,
                            user=self.user,
                        ).get_memories(
                            user_input=user_input,
                            limit=top_results,
                            min_relevance_score=min_relevance_score,
                        )
                conversation_memories = FileReader(
                    agent_name=self.agent_name,
                    agent_config=self.agent.AGENT_CONFIG,
                    collection_number=c.get_conversation_id(),
                    ApiClient=self.ApiClient,
                    user=self.user,
                )
                conversation_context = await conversation_memories.get_memories(
                    user_input=user_input,
                    limit=top_results,
                    min_relevance_score=min_relevance_score,
                )
                if len(conversation_context) == int(top_results):
                    conversational_context_tokens = get_tokens(
                        " ".join(conversation_context)
                    )
                    if int(conversational_context_tokens) < 4000:
                        conversational_results = top_results * 2
                        conversation_context = await conversation_memories.get_memories(
                            user_input=user_input,
                            limit=conversational_results,
                            min_relevance_score=min_relevance_score,
                        )
                        conversational_context_tokens = get_tokens(
                            " ".join(conversation_context)
                        )
                        if int(conversational_context_tokens) < 4000:
                            conversational_results = conversational_results * 2
                            conversation_context = (
                                await conversation_memories.get_memories(
                                    user_input=user_input,
                                    limit=conversational_results,
                                    min_relevance_score=min_relevance_score,
                                )
                            )
                context += conversation_context
            else:
                context = []
        if "context" in kwargs:
            context.append([kwargs["context"]])
        if vision_response != "":
            context.append(
                f"{self.agent_name}'s visual description from viewing uploaded images by user in this interaction:\n{vision_response}\n"
            )
        if context != [] and context != "":
            context = "\n".join(context)
            context = f"The user's input causes you remember these things:\n{context}\n\nIf referencing a file, paper, or website, cite sources.\n"
        else:
            context = ""
        working_directory = self.agent.working_directory
        helper_agent_name = self.agent_name
        if "helper_agent_name" not in kwargs:
            if "helper_agent_name" in self.agent.AGENT_CONFIG["settings"]:
                helper_agent_name = self.agent.AGENT_CONFIG["settings"][
                    "helper_agent_name"
                ]
        if "conversation_results" in kwargs:
            try:
                conversation_results = int(kwargs["conversation_results"])
            except:
                conversation_results = 5
        else:
            try:
                conversation_results = int(top_results) if top_results > 0 else 5
            except:
                conversation_results = 5
        conversation_history = ""
        if "interactions" in conversation:
            if conversation["interactions"] != []:
                activity_history = [
                    interaction
                    for interaction in conversation["interactions"]
                    if str(interaction["message"]).startswith("[ACTIVITY]")
                ]
                activities = []
                for activity in activity_history:
                    if "audio response" not in activity["message"]:
                        activities.append(activity)
                if len(activity_history) > 5:
                    activity_history = activity_history[-5:]
                interactions = []
                for interaction in conversation["interactions"]:
                    if (
                        not str(interaction["message"]).startswith("<audio controls>")
                        and not str(interaction["message"]).startswith("[ACTIVITY]")
                        and not str(interaction["message"]).startswith("[SUBACTIVITY]")
                    ):
                        timestamp = (
                            interaction["timestamp"]
                            if "timestamp" in interaction
                            else ""
                        )
                        role = interaction["role"] if "role" in interaction else ""
                        message = (
                            interaction["message"] if "message" in interaction else ""
                        )
                        message = regex.sub(r"(```.*?```)", "", message)
                        interactions.append(f"{timestamp} {role}: {message} \n ")
                if len(interactions) > 0:
                    interactions = interactions[-conversation_results:]
                    conversation_history = "\n".join(interactions)
                conversation_history += "\nThe assistant's recent activities:\n"
                for activity in activity_history:
                    timestamp = activity["timestamp"]
                    role = activity["role"]
                    message = str(activity["message"]).replace("[ACTIVITY]", "")
                    conversation_history += f"{timestamp} {role}: {message} \n "
        persona = ""
        if "persona" in prompt_args:
            if "PERSONA" in self.agent.AGENT_CONFIG["settings"]:
                persona = self.agent.AGENT_CONFIG["settings"]["PERSONA"]
            if "persona" in self.agent.AGENT_CONFIG["settings"]:
                persona = self.agent.AGENT_CONFIG["settings"]["persona"]
        if prompt_name == "Chat with Commands" and self.agent_commands == "":
            prompt_name = "Chat"
        file_contents = ""
        if "import_files" in prompt_args:
            file_reader = FileReader(
                agent_name=self.agent_name,
                agent_config=self.agent.AGENT_CONFIG,
                collection=4,
                user=self.user,
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
                file_path = os.path.normpath(working_directory, file_name)
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
                c.log_interaction(
                    role=self.agent_name,
                    message=f"I have read the file contents of {the_files}.",
                )
            else:
                the_files = "files."
            tokens_used = get_tokens(
                f"{prompt}{user_input}{all_files_content}{context}"
            )
            agent_max_tokens = int(
                self.agent.AGENT_CONFIG["settings"]["MAX_TOKENS"]
                if "MAX_TOKENS" in self.agent.AGENT_CONFIG["settings"]
                else 8192
            )
            if tokens_used > agent_max_tokens or files == []:
                fragmented_content = await file_reader.get_memories(
                    user_input=f"{user_input} {file_list}",
                    min_relevance_score=0.3,
                    limit=top_results if top_results > 0 else 5,
                )
                if fragmented_content != "":
                    file_contents = f"Here is some potentially relevant information from {the_files}\n{fragmented_content}\n\n"
        command_list = [
            available_command["friendly_name"]
            for available_command in self.agent.available_commands
            if available_command["enabled"] == True
        ]
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
            COMMANDS=self.agent_commands if len(command_list) > 0 else "",
            context=context,
            command_list=self.agent_commands if len(command_list) > 0 else "",
            date=datetime.now().strftime("%B %d, %Y %I:%M %p"),
            working_directory=working_directory,
            helper_agent_name=helper_agent_name,
            conversation_history=conversation_history,
            persona=persona,
            import_files=file_contents,
            **args,
        )
        tokens = get_tokens(formatted_prompt)
        return formatted_prompt, prompt, tokens

    async def run(
        self,
        user_input: str = "",
        context_results: int = 5,
        shots: int = 1,
        disable_memory: bool = True,
        conversation_name: str = "",
        browse_links: bool = False,
        persist_context_in_history: bool = False,
        images: list = [],
        searching: bool = False,
        log_user_input: bool = True,
        log_output: bool = True,
        **kwargs,
    ):
        global AGIXT_URI
        for setting in self.agent.AGENT_CONFIG["settings"]:
            if setting not in kwargs:
                kwargs[setting] = self.agent.AGENT_CONFIG["settings"][setting]
        if shots == 0:
            shots = 1
        shots = int(shots)
        prompt = "Chat"
        prompt_category = "Default"
        if "prompt_category" in kwargs:
            prompt_category = kwargs["prompt_category"]
            del kwargs["prompt_category"]
        if "prompt_name" in kwargs:
            prompt = kwargs["prompt_name"]
            del kwargs["prompt_name"]
        if "prompt" in kwargs:
            prompt = kwargs["prompt"]
            del kwargs["prompt"]
        disable_memory = False if str(disable_memory).lower() == "false" else True
        if "disable_memory" in kwargs:
            disable_memory = (
                False if str(kwargs["disable_memory"]).lower() == "false" else True
            )
            del kwargs["disable_memory"]
        browse_links = True if str(browse_links).lower() == "true" else False
        if "browse_links" in kwargs:
            browse_links = (
                True if str(kwargs["browse_links"]).lower() == "true" else False
            )
            del kwargs["browse_links"]
        websearch = False
        websearch_depth = 3
        conversation_results = 5
        if "conversation_results" in kwargs:
            try:
                conversation_results = int(kwargs["conversation_results"])
            except:
                conversation_results = 5
            del kwargs["conversation_results"]
        if "websearch" in self.agent.AGENT_CONFIG["settings"]:
            websearch = (
                str(self.agent.AGENT_CONFIG["settings"]["websearch"]).lower() == "true"
            )
        if "websearch_depth" in self.agent.AGENT_CONFIG["settings"]:
            websearch_depth = int(
                self.agent.AGENT_CONFIG["settings"]["websearch_depth"]
            )
        if "browse_links" in self.agent.AGENT_CONFIG["settings"]:
            browse_links = (
                str(self.agent.AGENT_CONFIG["settings"]["browse_links"]).lower()
                == "true"
            )
        if "websearch" in kwargs:
            websearch = True if str(kwargs["websearch"]).lower() == "true" else False
            del kwargs["websearch"]
        if "websearch_depth" in kwargs:
            try:
                websearch_depth = int(kwargs["websearch_depth"])
            except:
                websearch_depth = 3
            del kwargs["websearch_depth"]
        if "WEBSEARCH_TIMEOUT" in kwargs:
            try:
                websearch_timeout = int(kwargs["WEBSEARCH_TIMEOUT"])
            except:
                websearch_timeout = 0
        else:
            websearch_timeout = 0
        if "conversation_name" in kwargs:
            conversation_name = kwargs["conversation_name"]
        if conversation_name == "":
            conversation_name = "-"
        c = Conversations(conversation_name=conversation_name, user=self.user)
        async_tasks = []
        vision_response = ""
        if "vision_provider" in self.agent.AGENT_CONFIG["settings"]:
            if (
                images != []
                and self.agent.VISION_PROVIDER != "None"
                and self.agent.VISION_PROVIDER != ""
                and self.agent.VISION_PROVIDER != None
            ):
                logging.info(f"Getting vision response for images: {images}")
                message = "Viewing images." if len(images) > 1 else "Viewing image."
                c.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY] {message}",
                )
                try:
                    vision_response = await self.agent.vision_inference(
                        prompt=user_input, images=images
                    )
                    logging.info(f"Vision Response: {vision_response}")
                except Exception as e:
                    c.log_interaction(
                        role=self.agent_name,
                        message=f"[ACTIVITY][ERROR] Unable to view image.",
                    )
                    logging.error(f"Error getting vision response: {e}")
        if self.websearch == None or self.websearch.collection_number == "1":
            conversation_id = c.get_conversation_id()
            self.websearch = Websearch(
                collection_number=str(conversation_id),
                agent=self.agent,
                user=self.user,
                ApiClient=self.ApiClient,
            )
        if browse_links != False and websearch == False and searching == False:
            task = asyncio.create_task(
                self.websearch.scrape_websites(
                    user_input=user_input,
                    search_depth=websearch_depth,
                    summarize_content=False,
                    conversation_name=conversation_name,
                )
            )
            async_tasks.append(task)
        # Any other research prompt and action can be added here on bool toggle such as `websearch` and `browse_links`
        # Add them as asyncio tasks to the async_tasks list
        if websearch and searching == False:
            if browse_links != False and searching == False:
                task = asyncio.create_task(
                    self.websearch.scrape_websites(
                        user_input=user_input,
                        search_depth=websearch_depth,
                        summarize_content=False,
                        conversation_name=conversation_name,
                    )
                )
                async_tasks.append(task)
            if user_input == "":
                if "primary_objective" in kwargs and "task" in kwargs:
                    user_input = f"Primary Objective: {kwargs['primary_objective']}\n\nTask: {kwargs['task']}"
                else:
                    user_input = ""
            if user_input != "":
                searching_activity_id = c.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY] Searching for information.",
                )
                to_search_or_not_to_search = await self.run(
                    prompt_name="WebSearch Decision",
                    prompt_category="Default",
                    user_input=user_input,
                    context_results=context_results,
                    conversation_results=4,
                    conversation_name=conversation_name,
                    log_user_input=False,
                    log_output=False,
                    browse_links=False,
                    websearch=False,
                    tts=False,
                    searching=True,
                )
                to_search = re.search(
                    r"\byes\b", str(to_search_or_not_to_search).lower()
                )
                if to_search:
                    search_strings = await self.run(
                        prompt_name="WebSearch",
                        prompt_category="Default",
                        user_input=user_input,
                        context_results=context_results,
                        conversation_results=10,
                        conversation_name=conversation_name,
                        log_user_input=False,
                        log_output=False,
                        browse_links=False,
                        websearch=False,
                        tts=False,
                        searching=True,
                    )
                    if "```json" in search_strings:
                        search_strings = (
                            search_strings.split("```json")[1].split("```")[0].strip()
                        )
                    elif "```" in search_strings:
                        search_strings = search_strings.split("```")[1].strip()
                    try:
                        search_suggestions = json.loads(search_strings)
                    except:
                        keywords = extract_keywords(text=str(search_strings), limit=5)
                        if keywords:
                            search_string = " ".join(keywords)
                            # add month and year to the end of the search string
                            search_string += f" {datetime.now().strftime('%B %Y')}"
                        search_suggestions = [
                            {"search_string_suggestion_1": search_string}
                        ]
                    search_strings = []
                    if search_suggestions != []:
                        for i in range(1, int(websearch_depth) + 1):
                            if f"search_string_suggestion_{i}" in search_suggestions:
                                search_string = search_suggestions[
                                    f"search_string_suggestion_{i}"
                                ]
                                search_strings.append(search_string)
                                search_task = asyncio.create_task(
                                    self.websearch.websearch_agent(
                                        user_input=user_input,
                                        search_string=search_string,
                                        websearch_depth=websearch_depth,
                                        websearch_timeout=websearch_timeout,
                                        conversation_name=conversation_name,
                                        activity_id=searching_activity_id,
                                    )
                                )
                                async_tasks.append(search_task)
        await asyncio.gather(*async_tasks)
        formatted_prompt, unformatted_prompt, tokens = await self.format_prompt(
            user_input=user_input,
            top_results=int(context_results),
            conversation_results=conversation_results,
            prompt=prompt,
            prompt_category=prompt_category,
            conversation_name=conversation_name,
            websearch=websearch,
            searching=searching,
            vision_response=vision_response,
            **kwargs,
        )
        logging.info(f"Formatted Prompt: {formatted_prompt}")
        log_message = (
            user_input
            if user_input != "" and persist_context_in_history == False
            else formatted_prompt
        )
        if log_user_input:
            c.log_interaction(
                role="USER",
                message=log_message,
            )
        try:
            self.response = await self.agent.inference(
                prompt=formatted_prompt, tokens=tokens
            )
        except Exception as e:
            # Log the error with the full traceback for the provider
            error = ""
            for err in e:
                error += f"{err.args}\n{err.name}\n{err.msg}\n"
            logging.warning(f"TOKENS: {tokens} PROMPT CONTENT: {formatted_prompt}")
            logging.error(f"{self.agent.PROVIDER} Error: {error}")
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY][ERROR] Unable to generate response.",
            )
            return f"Unable to retrieve response."
        # Handle commands if the prompt contains the {COMMANDS} placeholder
        # We handle command injection that DOESN'T allow command execution by using {command_list} in the prompt
        if "{COMMANDS}" in unformatted_prompt:
            await self.execution_agent(conversation_name=conversation_name)
        if self.response != "" and self.response != None:
            agent_settings = self.agent.AGENT_CONFIG["settings"]
            if "<audio controls>" in self.response:
                self.response = re.sub(
                    r"<audio controls>(.*?)</audio>", "", self.response, flags=re.DOTALL
                )
            if "<image src=" in self.response:
                self.response = re.sub(
                    r"<image src=(.*?)>", "", self.response, flags=re.DOTALL
                )
            if log_output:
                c.log_interaction(
                    role=self.agent_name,
                    message=self.response,
                )
            tts = False
            if "tts" in kwargs:
                tts = str(kwargs["tts"]).lower() == "true"
            if "tts_provider" in agent_settings and tts == True:
                if (
                    agent_settings["tts_provider"] != "None"
                    and agent_settings["tts_provider"] != ""
                    and agent_settings["tts_provider"] != None
                ):
                    try:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[ACTIVITY] Generating audio response.",
                        )
                        tts_response = await self.agent.text_to_speech(
                            text=self.response
                        )
                        if not str(tts_response).startswith("http"):
                            file_type = "wav"
                            file_name = f"{uuid.uuid4().hex}.{file_type}"
                            audio_path = os.path.join(
                                self.agent.working_directory, file_name
                            )
                            audio_data = base64.b64decode(tts_response)
                            with open(audio_path, "wb") as f:
                                f.write(audio_data)
                            tts_response = f'<audio controls><source src="{AGIXT_URI}/outputs/{self.agent.agent_id}/{file_name}" type="audio/wav"></audio>'
                            c.log_interaction(
                                role=self.agent_name, message=tts_response
                            )
                    except Exception as e:
                        logging.warning(f"Failed to get TTS response: {e}")
            if disable_memory != True:
                try:
                    await self.agent_memory.write_text_to_memory(
                        user_input=user_input,
                        text=self.response,
                        external_source="user input",
                    )
                except:
                    pass
            if "image_provider" in agent_settings:
                if (
                    agent_settings["image_provider"] != "None"
                    and agent_settings["image_provider"] != ""
                    and agent_settings["image_provider"] != None
                    and agent_settings["image_provider"] != "default"
                ):
                    img_gen_prompt = f"Users message: {user_input} \n\n{'The user uploaded an image, one does not need generated unless the user is specifically asking.' if images else ''} **The assistant is acting as sentiment analysis expert and only responds with a concise YES or NO answer on if the user would like a creative generated image to be generated by AI in their request. No other explanation is needed!**\nWould the user potentially like an image generated based on their message?\nAssistant: "
                    create_img = await self.agent.inference(prompt=img_gen_prompt)
                    create_img = str(create_img).lower()
                    logging.info(f"Image Generation Decision Response: {create_img}")
                    to_create_image = re.search(r"\byes\b", str(create_img).lower())
                    if to_create_image:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[ACTIVITY] Generating image.",
                        )
                        img_prompt = f"**The assistant is acting as a Stable Diffusion Prompt Generator.**\n\nUsers message: {user_input} \nAssistant response: {self.response} \n\nImportant rules to follow:\n- Describe subjects in detail, specify image type (e.g., digital illustration), art style (e.g., steampunk), and background. Include art inspirations (e.g., Art Station, specific artists). Detail lighting, camera (type, lens, view), and render (resolution, style). The weight of a keyword can be adjusted by using the syntax (((keyword))) , put only those keyword inside ((())) which is very important because it will have more impact so anything wrong will result in unwanted picture so be careful. Realistic prompts: exclude artist, specify lens. Separate with double lines. Max 60 words, avoiding 'real' for fantastical.\n- Based on the message from the user and response of the assistant, you will need to generate one detailed stable diffusion image generation prompt based on the context of the conversation to accompany the assistant response.\n- The prompt can only be up to 60 words long, so try to be concise while using enough descriptive words to make a proper prompt.\n- Following all rules will result in a $2000 tip that you can spend on anything!\n- Must be in markdown code block to be parsed out and only provide prompt in the code block, nothing else.\nStable Diffusion Prompt Generator: "
                        image_generation_prompt = await self.agent.inference(
                            prompt=img_prompt
                        )
                        image_generation_prompt = str(image_generation_prompt)
                        if "```markdown" in image_generation_prompt:
                            image_generation_prompt = image_generation_prompt.split(
                                "```markdown"
                            )[1]
                            image_generation_prompt = image_generation_prompt.split(
                                "```"
                            )[0]
                        try:
                            generated_image = await self.agent.generate_image(
                                prompt=image_generation_prompt
                            )
                            c.log_interaction(
                                role=self.agent_name,
                                message=f"![Image generated by {self.agent_name}]({generated_image})",
                            )
                        except:
                            logging.warning(
                                f"Failed to generate image for prompt: {image_generation_prompt}"
                            )
        if shots > 1:
            responses = [self.response]
            for shot in range(shots - 1):
                prompt_args = {
                    "user_input": user_input,
                    "context_results": context_results,
                    "conversation_results": conversation_results,
                    "conversation_name": conversation_name,
                    "disable_memory": disable_memory,
                    **kwargs,
                }
                if "images" in prompt_args:
                    del prompt_args["images"]
                if "searching" in prompt_args:
                    del prompt_args["searching"]
                if "tts" in prompt_args:
                    del prompt_args["tts"]
                if "websearch" in prompt_args:
                    del prompt_args["websearch"]
                if "websearch_depth" in prompt_args:
                    del prompt_args["websearch_depth"]
                if "browse_links" in prompt_args:
                    del prompt_args["browse_links"]

                shot_response = await self.run(
                    agent_name=self.agent_name,
                    prompt_name=prompt,
                    prompt_category=prompt_category,
                    log_user_input=False,
                    log_output=False,
                    websearch=False,
                    browse_links=False,
                    searching=True,
                    tts=False,
                    **prompt_args,
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
        ch = Chain(user=self.user)
        chains = ch.get_chains()
        chain_name = f"{agent_name} Command Suggestions"
        if chain_name in chains:
            step = int(ch.get_chain(chain_name=chain_name)["steps"][-1]["step"]) + 1
        else:
            ch.add_chain(chain_name=chain_name)
            step = 1
        ch.add_chain_step(
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
        c = Conversations(conversation_name=conversation_name, user=self.user)
        command_list = [
            available_command["friendly_name"]
            for available_command in self.agent.available_commands
            if available_command["enabled"] == True
        ]
        logging.info(f"Agent command list: {command_list}")
        if len(command_list) > 0:
            commands_to_execute = re.findall(r"#execute\((.*?)\)", self.response)
            reformatted_response = self.response
            if len(commands_to_execute) > 0:
                for command in commands_to_execute:
                    command_name = str(command.split(",")[0])
                    if command_name.startswith(" "):
                        command_name = command_name[1:]
                    if command_name.endswith(" "):
                        command_name = command_name[:-1]
                    command_name = command_name.replace("'", "").replace('"', "")
                    if (
                        command_name != ""
                        and command_name != None
                        and command_name != "None"
                    ):
                        if len(command.split(",")[1:]) > 0:
                            try:
                                command_args = json.loads(
                                    '{"command_args": '
                                    + ",".join(command.split(",")[1:])
                                    + "}"
                                )
                            except:
                                command_args = {}
                        else:
                            command_args = {}
                        if "command_args" in command_args:
                            command_args = command_args["command_args"]
                        logging.info(f"Command to execute: {command_name}")
                        logging.info(f"Command Args: {command_args}")
                        if command_name not in command_list:
                            # Ask the agent for clarification on which command should be executed.
                            command_output = self.ApiClient.prompt_agent(
                                agent_name=self.agent_name,
                                prompt_name="Command Clarification",
                                prompt_args={
                                    "command_name": command_name,
                                    "command_args": json.dumps(command_args),
                                    "conversation_name": "AGiXT Terminal",
                                },
                            )
                        else:
                            try:
                                c.log_interaction(
                                    role=self.agent_name,
                                    message=f"[ACTIVITY] Executing command `{command_name}` with args `{command_args}`.",
                                )
                                ext = Extensions(
                                    agent_name=self.agent_name,
                                    agent_config=self.agent.AGENT_CONFIG,
                                    conversation_name=conversation_name,
                                    ApiClient=self.ApiClient,
                                    user=self.user,
                                )
                                command_output = await ext.execute_command(
                                    command_name=command_name,
                                    command_args=command_args,
                                )
                                formatted_output = f"```\n{command_output}\n```"
                                command_output = f"**Executed Command:** `{command_name}` with the following parameters:\n```json\n{json.dumps(command_args, indent=4)}\n```\n\n**Command Output:**\n{formatted_output}"
                            except Exception as e:
                                logging.error(
                                    f"Error: {self.agent_name} failed to execute command `{command_name}`. {e}"
                                )
                                c.log_interaction(
                                    role=self.agent_name,
                                    message=f"[ACTIVITY][ERROR] Failed to execute command `{command_name}`.",
                                )
                                command_output = f"**Failed to execute command `{command_name}` with args `{command_args}`. Please try again.**"
                        if command_output:
                            c.log_interaction(
                                role=self.agent_name,
                                message=f"[ACTIVITY] {command_output}",
                            )
                            reformatted_response = reformatted_response.replace(
                                f"#execute({command_name}, {command_args})",
                                (
                                    json.dumps(command_output)
                                    if isinstance(command_output, dict)
                                    else command_output
                                ),
                            )
                        if reformatted_response != self.response:
                            self.response = reformatted_response
