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
from Memories import Memories
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
from MagicalAuth import MagicalAuth, impersonate_user
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
        collection_id: str = "0",
    ):
        self.ApiClient = ApiClient
        self.user = user
        self.auth = MagicalAuth(token=impersonate_user(email=self.user))
        self.uri = getenv("AGIXT_URI")
        if agent_name != "":
            self.agent_name = agent_name
            self.agent = Agent(self.agent_name, user=user, ApiClient=self.ApiClient)
            self.websearch = Websearch(
                collection_number=collection_id,
                agent=self.agent,
                user=self.user,
                ApiClient=self.ApiClient,
            )
            self.agent_memory = Memories(
                agent_name=self.agent_name,
                agent_config=self.agent.AGENT_CONFIG,
                collection_number="0",
                ApiClient=self.ApiClient,
                user=self.user,
            )
            self.outputs = f"{self.uri}/outputs/{self.agent.agent_id}"
        else:
            self.agent_name = ""
            self.agent = None
            self.websearch = None
            self.agent_memory = None
            self.outputs = f"{self.uri}/outputs"
        self.response = ""
        self.failures = 0
        self.chain = Chain(user=user)
        self.cp = Prompts(user=user)
        self._processed_commands = set()

    def custom_format(self, string, **kwargs):
        if "fp" in kwargs:
            return kwargs["user_input"]
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
        conversation_id = c.get_conversation_id()
        conversation_outputs = (
            f"http://localhost:7437/outputs/{self.agent.agent_id}/{conversation_id}/"
        )
        context = []
        if int(top_results) > 0:
            if user_input:
                min_relevance_score = 0.2
                if "min_relevance_score" in kwargs:
                    try:
                        min_relevance_score = float(kwargs["min_relevance_score"])
                    except:
                        min_relevance_score = 0.2
                context += await self.agent_memory.get_memories(
                    user_input=user_input,
                    limit=top_results,
                    min_relevance_score=min_relevance_score,
                )
                if "inject_memories_from_collection_number" in kwargs:
                    collection_id = kwargs["inject_memories_from_collection_number"]
                    try:
                        context += await Memories(
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
                    except Exception as e:
                        logging.error(
                            f"Error: {self.agent_name} failed to get memories from collection {collection_id}. {e}"
                        )
                conversation_context = await self.websearch.agent_memory.get_memories(
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
                        conversation_context = (
                            await self.websearch.agent_memory.get_memories(
                                user_input=user_input,
                                limit=conversational_results,
                                min_relevance_score=min_relevance_score,
                            )
                        )
                        conversational_context_tokens = get_tokens(
                            " ".join(conversation_context)
                        )
                        if int(conversational_context_tokens) < 4000:
                            conversational_results = conversational_results * 2
                            conversation_context = (
                                await self.websearch.agent_memory.get_memories(
                                    user_input=user_input,
                                    limit=conversational_results,
                                    min_relevance_score=min_relevance_score,
                                )
                            )
                context += conversation_context
        if "context" in kwargs:
            context.append(kwargs["context"])
        include_sources = (
            str(kwargs["include_sources"]).lower() == "true"
            if "include_sources" in kwargs
            else False
        )
        if include_sources:
            sources = []
            for line in context:
                if "Content from" in line:
                    source = line.split("Content from ")[1].split("\n")[0]
                    if f"Content from {source}" not in sources:
                        sources.append(f"Content from {source}")
            if sources != []:
                joined_sources = "\n".join(sources)
                thinking_id = c.get_thinking_id(agent_name=self.agent_name)
                source_count = len(sources)
                c.log_interaction(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{thinking_id}] Referencing {source_count} sources from content.\n{joined_sources}.",
                )
        working_directory = f"{self.agent.working_directory}/{conversation_id}"
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
        agent_tasks = self.agent.get_conversation_tasks(conversation_id=conversation_id)
        if agent_tasks != "":
            context.append(agent_tasks)
        conversation_history = ""
        conversation = c.get_conversation()
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
                conversation_history += "\n## The assistant's recent activities:\n"
                conversation_history += c.get_activities_with_subactivities()
        if conversation_history != "":
            context.append(
                f"### Recent Activities and Conversation History\n{conversation_history}\n"
            )
        persona = ""
        if "PERSONA" in self.agent.AGENT_CONFIG["settings"]:
            persona = self.agent.AGENT_CONFIG["settings"]["PERSONA"]
        if "persona" in self.agent.AGENT_CONFIG["settings"]:
            persona = self.agent.AGENT_CONFIG["settings"]["persona"]
        try:
            company_id = self.auth.company_id
            if "company_id" in kwargs:
                company_id = kwargs["company_id"]
            if company_id:
                company_training = self.auth.get_training_data(company_id=company_id)
                persona += f"\n\n**Guidelines as they pertain to the company:**\n{company_training}"
                cs = self.auth.get_company_agent_session(company_id=company_id)
                company_memories = cs.get_agent_memories(
                    agent_name="AGiXT", user_input=user_input
                )
                if company_memories:
                    for result in company_memories:
                        metadata = (
                            result["additional_metadata"]
                            if "additional_metadata" in result
                            else ""
                        )
                        external_source = (
                            result["external_source_name"]
                            if "external_source_name" in result
                            else None
                        )
                        timestamp = (
                            result["timestamp"]
                            if "timestamp" in result
                            else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        )
                        if external_source:
                            metadata = f"Sourced from {external_source}:\nSourced on: {timestamp}\n{metadata}"
                        if metadata not in context and metadata != "":
                            context.append(metadata)
        except Exception as e:
            pass
        if persona != "":
            context.append(
                f"## Persona\n**The assistant follows a persona and uses the following guidelines and information to remain in character.**\n{persona}\nThe assistant is {self.agent_name} and is an AGiXT agent created by DevXT, empowered with AGiXT abilities."
            )
        if "72" in kwargs and "42" in kwargs:
            if kwargs["72"] == True and kwargs["42"] == True:
                kwargs["fp"] = context
        if "uploaded_file_data" in kwargs:
            context.append(
                f"The user uploaded these files for the assistant to analyze:\n{kwargs['uploaded_file_data']}\n"
            )
        if vision_response != "":
            context.append(
                f"The assistant's visual description from viewing uploaded images by user in this interaction:\n{vision_response}\n"
            )
        if "data_analysis" in kwargs:
            context.append(
                f"The assistant's data analysis from the user's input and file uploads:\n{kwargs['data_analysis']}\n"
            )
        if context != [] and context != "":
            if isinstance(context, list):
                context = "\n".join(context)
            context = f"The user's input causes the assistant to recall these memories from activities:\n{context}\n\n**If referencing a file or image from context to the user, link to it with a url at `{conversation_outputs}the_file_name` - The URL is accessible to the user. If the file has not been referenced in context or from activities, do not attempt to link to it as it may not exist. Use exact file names and links from context only.** .\n"
        else:
            context = ""
        file_contents = ""
        if "import_files" in prompt_args:
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
                memories = Memories(
                    agent_name=self.agent_name,
                    agent_config=self.agent.AGENT_CONFIG,
                    collection_number="1",
                    ApiClient=self.ApiClient,
                    user=self.user,
                )
                fragmented_content = await memories.get_memories(
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
            "output_url",
        ]
        args = kwargs.copy()
        for arg in kwargs:
            if arg in skip_args:
                del args[arg]
        agent_commands = ""
        if "disable_commands" not in kwargs:
            agent_commands = self.agent.get_commands_prompt(
                conversation_id=conversation_id
            )
        formatted_prompt = self.custom_format(
            string=prompt,
            user_input=user_input,
            agent_name=self.agent_name,
            COMMANDS=agent_commands,
            context=context,
            command_list=agent_commands,
            date=datetime.now().strftime("%B %d, %Y %I:%M %p"),
            working_directory=working_directory,
            helper_agent_name=helper_agent_name,
            conversation_history=conversation_history,
            persona=persona,
            import_files=file_contents,
            output_url=conversation_outputs,
            **args,
        )
        tokens = get_tokens(formatted_prompt)
        return formatted_prompt, prompt, tokens

    def process_thinking_tags(
        self, response: str, thinking_id: str, c: Conversations
    ) -> str:
        """
        Process thinking and reflection tags in the response and log them as subactivities.
        Only processes new, unprocessed tags.

        Args:
            response: The response text containing thinking/reflection tags
            thinking_id: ID for the thinking activity
            c: Conversation object for logging interactions

        Returns:
            Updated response with processed tags
        """
        # Pattern to match thinking and reflection tags and their content
        tag_pattern = (
            r"<(thinking|reflection)>(.*?)(?=<(?:thinking|reflection|answer)|$)"
        )

        # Find all matches
        matches = list(re.finditer(tag_pattern, response, re.DOTALL))

        # Keep track of processed tags using content as key to avoid duplicates
        if not hasattr(self, "_processed_tags"):
            self._processed_tags = set()

        # Create a dict to store unique thoughts by their cleaned content
        unique_thoughts = {}

        for match in matches:
            tag_name = match.group(1)  # thinking or reflection
            tag_content = match.group(2).strip()

            # Clean the content
            cleaned_content = tag_content
            cleaned_content = re.sub(
                r"<execute>.*?</execute>", "", cleaned_content, flags=re.DOTALL
            )
            cleaned_content = re.sub(
                r"<output>.*?</output>", "", cleaned_content, flags=re.DOTALL
            )
            cleaned_content = re.sub(r"<rate>.*?</rate>", "", cleaned_content)
            cleaned_content = re.sub(r"<reward>.*?</reward>", "", cleaned_content)
            cleaned_content = re.sub(r"<count>.*?</count>", "", cleaned_content)
            cleaned_content = cleaned_content.replace("\n\\n", "\n")
            cleaned_content = cleaned_content.replace("</reflection>", "")
            cleaned_content = cleaned_content.replace("</thinking>", "")
            cleaned_content = cleaned_content.replace("<output>", "")
            cleaned_content = cleaned_content.replace("</output>", "")
            cleaned_content = cleaned_content.replace("<step>", "")
            cleaned_content = cleaned_content.replace("</step>", "")
            cleaned_content = re.sub(
                r"<name>.*?</name>", "", cleaned_content, flags=re.DOTALL
            )
            cleaned_content = re.sub(r"\n\s*\n\s*\n", "\n\n", cleaned_content)
            cleaned_content = cleaned_content.strip()

            # Use cleaned content as key to prevent duplicates
            if cleaned_content and cleaned_content not in unique_thoughts:
                unique_thoughts[cleaned_content] = {
                    "tag_name": tag_name,
                    "content": cleaned_content,
                }

        # Log only unique thoughts
        for thought in unique_thoughts.values():
            tag_name = str(thought["tag_name"]).lower()
            content = thought["content"]
            content = re.sub(r"\. ", ".\n", content, count=1)
            if content.startswith("1."):
                # Remove the first 3 character of the string
                content = content[3:]
                content = re.sub(r"\. ", ".\n", content, count=1)

            # Create a unique identifier for this tag
            tag_identifier = f"{tag_name}:{content}"

            # Only log if we haven't seen this exact thought before
            if tag_identifier not in self._processed_tags:
                # log_message = f"[SUBACTIVITY][{thinking_id}] **{tag_name.title()}:** {content}"
                if tag_name == "thinking":
                    log_message = f"[SUBACTIVITY][{thinking_id}][THOUGHT] {content}"
                elif tag_name == "reflection":
                    log_message = f"[SUBACTIVITY][{thinking_id}][REFLECTION] {content}"
                else:
                    log_message = f"[SUBACTIVITY][{thinking_id}] {content}"
                c.log_interaction(role=self.agent_name, message=log_message)
                self._processed_tags.add(tag_identifier)

        return response

    async def run(
        self,
        user_input: str = "",
        context_results: int = 100,
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
        context_results = 5 if not context_results else int(context_results)
        prompt = "Think About It"
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
        kwargs["72"] = self.agent_name.lower().startswith("nu") == True
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
        if "collection_number" in kwargs:
            collection_number = str(kwargs["collection_number"])
            self.websearch = Websearch(
                collection_number=collection_number,
                agent=self.agent,
                user=self.user,
                ApiClient=self.ApiClient,
            )
            del kwargs["collection_number"]
        use_smartest = False
        if "use_smartest" in kwargs:
            use_smartest = (
                True if str(kwargs["use_smartest"]).lower() == "true" else False
            )
            del kwargs["use_smartest"]
        websearch = False
        websearch_depth = 3
        conversation_results = 5
        kwargs["42"] = self.agent_name[-3:].lower() == "pt"
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
                        prompt=user_input, images=images, use_smartest=use_smartest
                    )
                    logging.info(f"Vision Response: {vision_response}")
                except Exception as e:
                    c.log_interaction(
                        role=self.agent_name,
                        message=f"[ACTIVITY][ERROR] Unable to view image.",
                    )
                    logging.error(f"Error getting vision response: {e}")
        if browse_links != False and websearch == False and searching == False:
            task = asyncio.create_task(
                self.websearch.scrape_websites(
                    user_input=user_input,
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
                thinking_id = c.get_thinking_id(agent_name=self.agent_name)
                searching_activity_id = c.log_interaction(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{thinking_id}] Searching for information.",
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
        if self.outputs in formatted_prompt:
            # Anonymize AGiXT server URL to LLM
            formatted_prompt = formatted_prompt.replace(
                self.outputs, f"http://localhost:7437/outputs/{self.agent.agent_id}"
            )
        # logging.info(f"Formatted Prompt: {formatted_prompt}")
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
                prompt=formatted_prompt, use_smartest=use_smartest
            )
        except Exception as e:
            # Log the error with the full traceback for the provider
            error = ""
            for err in e:
                error += f"{err.args}\n{err.name}\n{err.msg}\n"
            # logging.warning(f"TOKENS: {tokens} PROMPT CONTENT: {formatted_prompt}")
            logging.error(f"{self.agent.PROVIDER} Error: {error} TOKENS: {tokens}")
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY][ERROR] Unable to generate response.",
            )
            return f"Unable to retrieve response."
        # Deanonymize AGiXT server URL to send back to the user
        self.response = self.response.replace(
            f"http://localhost:7437/outputs/{self.agent.agent_id}", self.outputs
        )
        if self.outputs in self.response:
            output_url_pattern = re.escape(self.outputs) + r"/\d+/([^\"'\s]+)"
            links = re.findall(output_url_pattern, self.response)
            if links:
                for file_ref in links:
                    # Construct the file path based on working directory and conversation ID
                    conversation_id = c.get_conversation_id() if "c" in locals() else ""
                    file_path = (
                        f"{self.agent.working_directory}/{conversation_id}/{file_ref}"
                    )

                    # If the file doesn't exist, look for similar files
                    if not os.path.exists(file_path):
                        # Get the directory and filename parts
                        dir_path = os.path.dirname(file_path)
                        file_name = os.path.basename(file_ref)
                        extension = os.path.splitext(file_name)[1]

                        # If the directory exists, look for alternative files
                        if os.path.exists(dir_path):
                            best_match = None
                            highest_similarity = 0
                            most_recent_match = None
                            most_recent_time = 0

                            # Look for files with the same extension
                            for candidate in os.listdir(dir_path):
                                candidate_path = os.path.join(dir_path, candidate)
                                if os.path.isfile(
                                    candidate_path
                                ) and candidate.endswith(extension):
                                    # Check file creation/modification time
                                    file_time = os.path.getmtime(candidate_path)

                                    # Calculate similarity between filenames
                                    from difflib import SequenceMatcher

                                    similarity = SequenceMatcher(
                                        None, file_name, candidate
                                    ).ratio()

                                    # Track the most similar file
                                    if similarity > highest_similarity:
                                        highest_similarity = similarity
                                        best_match = candidate

                                    # Track the most recently modified file with same extension
                                    if file_time > most_recent_time:
                                        most_recent_time = file_time
                                        most_recent_match = candidate

                            # Prefer recently created files (within last 5 minutes) over similar names
                            if most_recent_match and (
                                time.time() - most_recent_time < 300
                            ):
                                replacement = most_recent_match
                            # Fall back to the most similar filename if similarity is reasonable
                            elif best_match and highest_similarity > 0.6:
                                replacement = best_match
                            else:
                                # No good replacement found
                                continue

                            # Replace the broken link with the found file
                            orig_url = f"{self.outputs}/{conversation_id}/{file_ref}"
                            new_url = f"{self.outputs}/{conversation_id}/{replacement}"
                            self.response = self.response.replace(orig_url, new_url)

                            logging.info(
                                f"Replaced file reference from {file_ref} to {replacement}"
                            )

        # Handle commands if the prompt contains the {COMMANDS} placeholder
        # We handle command injection that DOESN'T allow command execution by using {command_list} in the prompt
        if "<think>" in self.response:
            self.response.replace("<think>", "<thinking>")
            self.response.replace("</think>", "</thinking>")
        if "<thinking>" in self.response:
            thinking_id = c.get_thinking_id(agent_name=self.agent_name)
            # Iterate over each thinking tag to the end of the </thinking> or next <thinking> or <answer> tag or <reflection> tag
            # There may or may not be a closing tag.
            # We want to do a log interaction per <thinking> and <reflection> tag until the next `<` in this format:
            # [SUBACTIVITY][{thinking_id}] **{tag_name}** {tag_content}
            self.response = self.process_thinking_tags(
                response=self.response, thinking_id=thinking_id, c=c
            )

        if "{COMMANDS}" in unformatted_prompt and "disable_commands" not in kwargs:
            self._processed_commands = set()
            processed_length = 0
            no_changes = 0
            # Then enter the main processing loop
            while True:
                if "<think>" in self.response:
                    self.response.replace("<think>", "<thinking>")
                    self.response.replace("</think>", "</thinking>")
                if "<thinking>" in self.response:
                    thinking_id = c.get_thinking_id(agent_name=self.agent_name)
                    self.response = self.process_thinking_tags(
                        response=self.response, thinking_id=thinking_id, c=c
                    )
                # First handle any initial commands
                if "<execute>" in self.response:
                    await self.execution_agent(conversation_name=conversation_name)
                    new_processed_length = len(self.response)
                    if new_processed_length > processed_length:
                        # Get continuation only if we got new content
                        # Make the context about command execution clearer
                        command_output = self.response[processed_length:].strip()
                        new_prompt = f"{formatted_prompt}\n\n{self.agent_name}: {self.response[:processed_length]}\n\nCommand executed with output: {command_output}\n\nThe assistant should continue its thought process based on this command output..."
                        command_response = await self.agent.inference(
                            prompt=new_prompt, use_smartest=use_smartest
                        )
                        self.response = f"{self.response}{command_response}"
                        processed_length = new_processed_length
                    else:
                        if "<execute>" not in self.response[processed_length:]:
                            break
                if "<think>" in self.response:
                    self.response.replace("<think>", "<thinking>")
                    self.response.replace("</think>", "</thinking>")
                if "<thinking>" in self.response:
                    thinking_id = c.get_thinking_id(agent_name=self.agent_name)
                    self.response = self.process_thinking_tags(
                        response=self.response, thinking_id=thinking_id, c=c
                    )
                # Check if we have new commands to process
                if (
                    "</output>" in self.response[processed_length:]
                    or "<execute>" in self.response[processed_length:]
                ):
                    if "<think>" in self.response:
                        self.response.replace("<think>", "<thinking>")
                        self.response.replace("</think>", "</thinking>")
                    if "<thinking>" in self.response:
                        thinking_id = c.get_thinking_id(agent_name=self.agent_name)
                        self.response = self.process_thinking_tags(
                            response=self.response, thinking_id=thinking_id, c=c
                        )
                    await self.execution_agent(conversation_name=conversation_name)
                    new_processed_length = len(self.response)

                    if new_processed_length > processed_length:
                        # Only continue if we actually got new content
                        new_prompt = f"{formatted_prompt}\n\n{self.agent_name}: {self.response}\n\nThe assistant has executed a command and should continue its thought process, the user does not see this message. Proceed with thinking, responding, or executing more commands before the response to the user. This can be used also to evaluate output of previously executed commands and retry executing a command if the output of the command was not as expected. The assistant should never try to fill in the command output, it will be returned to the assistant after the command is executed by the system. Ensure the <answer> block does not contain <thinking>, <reflection>, <execute>, or <output> tags, those should only exist before and after the <answer> block. The <answer> block should only contain the final, well reasoned response to the user."
                        command_response = await self.agent.inference(
                            prompt=new_prompt, use_smartest=use_smartest
                        )
                        self.response = f"{self.response}{command_response}"
                        processed_length = new_processed_length
                        # Check for new thinking tags after getting new content
                        if "<think>" in self.response:
                            self.response.replace("<think>", "<thinking>")
                            self.response.replace("</think>", "</thinking>")
                        if "<thinking>" in self.response:
                            thinking_id = c.get_thinking_id(agent_name=self.agent_name)
                            self.response = self.process_thinking_tags(
                                response=self.response, thinking_id=thinking_id, c=c
                            )
                    else:
                        break  # No new content, stop processing
                # If no answer block yet, try to get it
                elif "</answer>" not in self.response:
                    new_prompt = f"{formatted_prompt}\n\n{self.agent_name}: {self.response}\n\nWas the assistant {self.agent_name} done typing? If not, continue from where you left off without acknowledging this message or repeating anything that was already typed and the response will be appended. If the assistant needs to rewrite the response, start a new <answer> tag with the new response and close it with </answer> when complete. If the assistant was done, simply respond with '</answer>' as long as there is a <answer> block present, otherwise, the final answer to the user should be within the <answer> block. to send the message to the user. Ensure the <answer> block does not contain <thinking>, <reflection>, <execute>, or <output> tags, those should only exist before and after the <answer> block. The <answer> block should only contain the final, well reasoned response to the user."
                    response = await self.agent.inference(
                        prompt=new_prompt, use_smartest=use_smartest
                    )
                    self.response = f"{self.response}{response}"
                    continue
                else:
                    # We have an answer block - check if there are unprocessed commands before it
                    pre_answer = self.response.split("<answer>")[0]
                    if (
                        "<execute>" in pre_answer
                        and "</output>" not in pre_answer.split("<execute>")[-1]
                    ):
                        # There's an unprocessed command before the answer block
                        await self.execution_agent(conversation_name=conversation_name)
                        new_processed_length = len(self.response)
                        if new_processed_length > processed_length:
                            # Continue processing if we got new content
                            continue

                    answer_block = self.response.split("</answer>")[0].split(
                        "<answer>"
                    )[-1]
                    if "<thinking>" in answer_block:
                        self.response = self.response.replace("</answer>", "").replace(
                            "<answer>", ""
                        )
                    elif "<execute>" in answer_block:
                        self.response = self.response.replace("</answer>", "").replace(
                            "<answer>", ""
                        )
                    else:
                        break
                no_changes += 1
                if no_changes > 5:
                    last_closed_tag = self.response.rfind(">")
                    self.response = (
                        self.response[: last_closed_tag + 1]
                        + "<answer>"
                        + self.response[last_closed_tag + 1 :]
                    )
                    self.response += "</answer>"
        if "<think>" in self.response:
            self.response.replace("<think>", "<thinking>")
            self.response.replace("</think>", "</thinking>")
        if "<thinking>" in self.response:
            thinking_id = c.get_thinking_id(agent_name=self.agent_name)
            self.response = self.process_thinking_tags(
                response=self.response, thinking_id=thinking_id, c=c
            )
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
                            message=f"[SUBACTIVITY][{thinking_id}][EXECUTION] Generating audio response.",
                        )
                        answer = self.response.split("</answer>")[0].split("<answer>")[
                            -1
                        ]
                        tts_response = await self.agent.text_to_speech(text=answer)
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
                        self.response = f"{self.response}\n\n{tts_response}"
                        if "</answer>" in self.response:
                            self.response = self.response.replace("</answer>", "")
                            self.response += "</answer>"
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
                            message=f"[SUBACTIVITY][{thinking_id}][EXECUTION] Generating image.",
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
                            self.response = f"{self.response}\n![Image generated by {self.agent_name}]({generated_image})"
                            if "</answer>" in self.response:
                                self.response = self.response.replace("</answer>", "")
                                self.response += "</answer>"
                        except:
                            logging.warning(
                                f"Failed to generate image for prompt: {image_generation_prompt}"
                            )
            if "<thinking>" in self.response:
                thinking_id = c.get_thinking_id(agent_name=self.agent_name)
                self.response = self.process_thinking_tags(
                    response=self.response, thinking_id=thinking_id, c=c
                )
            if log_output:
                c.log_interaction(
                    role=self.agent_name,
                    message=self.response,
                )
        else:
            logging.info(f"{self.agent_name} Response: {self.response}")
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

    def extract_commands_from_response(self, response):
        # Extract all <execute>...</execute> blocks
        command_blocks = re.findall(r"(<execute>.*?</execute>)", response, re.DOTALL)
        extracted_commands = []
        for command_block in command_blocks:
            # Extract the content inside <execute>...</execute>
            command_content = re.search(
                r"<execute>(.*?)</execute>", command_block, re.DOTALL
            ).group(1)
            # Extract the command name
            name_match = re.search(r"<name>(.*?)</name>", command_content, re.DOTALL)
            if name_match:
                command_name = name_match.group(1).strip()
                # Remove the <name> tag from the command_content
                command_content_without_name = re.sub(
                    r"<name>.*?</name>", "", command_content, flags=re.DOTALL
                )
                # Extract arguments
                arg_matches = re.findall(
                    r"<(.*?)>(.*?)</\1>", command_content_without_name, re.DOTALL
                )
                args = {}
                for arg_name, arg_value in arg_matches:
                    args[arg_name] = arg_value.strip()
                extracted_commands.append((command_block, command_name, args))
        return extracted_commands

    async def execution_agent(self, conversation_name):
        c = Conversations(conversation_name=conversation_name, user=self.user)
        command_list = [
            available_command["friendly_name"]
            for available_command in self.agent.available_commands
            if available_command["enabled"] == True
        ]
        logging.info(f"Agent command list: {command_list}")
        thinking_id = c.get_thinking_id(agent_name=self.agent_name)
        # Extract commands from the response
        commands_to_execute = self.extract_commands_from_response(self.response)
        logging.debug(f"Commands to execute: {commands_to_execute}")
        reformatted_response = self.response
        if commands_to_execute:
            for command_block, command_name, command_args in commands_to_execute:
                position = self.response.index(command_block)
                command_id = f"{position}:{command_name}:{json.dumps(command_args, sort_keys=True)}"
                # Skip if we've already processed this exact command
                if command_id in self._processed_commands:
                    logging.debug(f"Skipping duplicate command: {command_id}")
                    continue

                # Mark this command as processed
                self._processed_commands.add(command_id)
                logging.info(f"Command to execute: {command_name}")
                logging.info(f"Command Args: {command_args}")

                command_output = ""
                if command_name.strip().lower() not in [
                    cmd.lower() for cmd in command_list
                ]:
                    command_output = f"Unknown command: {command_name}"
                    logging.warning(command_output)
                else:
                    try:
                        json_args = json.dumps(command_args, indent=2)
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{thinking_id}][EXECUTION] Executing `{command_name}`.\n```json\n{json_args}```",
                        )
                        ext = Extensions(
                            agent_name=self.agent_name,
                            agent_id=self.agent.agent_id,
                            agent_config=self.agent.AGENT_CONFIG,
                            conversation_name=conversation_name,
                            conversation_id=c.get_conversation_id(),
                            ApiClient=self.ApiClient,
                            api_key=self.ApiClient.headers["Authorization"],
                            user=self.user,
                        )
                        command_args["activity_id"] = thinking_id
                        command_output = await ext.execute_command(
                            command_name=command_name,
                            command_args=command_args,
                        )
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{thinking_id}][EXECUTION] `{command_name}` was executed successfully.\n{command_output}",
                        )
                        logging.info(f"Command output: {command_output}")
                    except Exception as e:
                        error_message = f"Error: {self.agent_name} failed to execute command `{command_name}`. {e}"
                        logging.error(error_message)
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{thinking_id}][ERROR] Failed to execute command `{command_name}`.\n{error_message}",
                        )
                        command_output = error_message
                # Format the command execution and output
                formatted_execution = (
                    f"<execute>\n"
                    f"<name>{command_name}</name>\n"
                    f"{chr(10).join([f'<{k}>{v}</{k}>' for k, v in command_args.items()])}\n"
                    f"</execute>\n"
                    f"<output>{command_output}</output>"
                )

                # Replace the original command block with the formatted execution and output
                reformatted_response = reformatted_response.replace(
                    command_block, formatted_execution, 1
                )
                logging.info(f"Command output: {command_output}")
        else:
            cmds = "\n".join(command_list)
            self.response += f"\nThe assistant tried to execute a command, but it was not recognized. Ensure that the correct naming of the commands is being used, they go off of the friendly name. Please choose from the list of available commands and try again:\n{cmds}"
        if reformatted_response != self.response:
            self.response = reformatted_response
