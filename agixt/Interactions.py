import os
import re
import regex
import json
import time
import logging
import tiktoken
import base64
import uuid
from datetime import datetime
from readers.website import WebsiteReader
from readers.file import FileReader
from readers.youtube import YoutubeReader
from Websearch import Websearch
from Extensions import Extensions
from ApiClient import (
    Agent,
    Prompts,
    Chain,
    log_interaction,
    get_conversation,
    AGIXT_URI,
)
from Defaults import DEFAULT_USER

logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def get_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(text))
    return num_tokens


class Interactions:
    def __init__(
        self,
        agent_name: str = "",
        collection_number: int = 0,
        user=DEFAULT_USER,
        ApiClient=None,
    ):
        if agent_name != "":
            self.agent_name = agent_name
            self.agent = Agent(self.agent_name, user=user, ApiClient=ApiClient)
            self.agent_commands = self.agent.get_commands_string()
            self.websearch = Websearch(
                agent_name=self.agent_name,
                agent_config=self.agent.AGENT_CONFIG,
                ApiClient=ApiClient,
                searxng_instance_url=(
                    self.agent.AGENT_CONFIG["settings"]["SEARXNG_INSTANCE_URL"]
                    if "SEARXNG_INSTANCE_URL" in self.agent.AGENT_CONFIG["settings"]
                    else ""
                ),
            )
        else:
            self.agent_name = ""
            self.agent = None
            self.agent_commands = ""
        self.agent_memory = WebsiteReader(
            agent_name=self.agent_name,
            agent_config=self.agent.AGENT_CONFIG,
            collection_number=int(collection_number),
            ApiClient=ApiClient,
            user=user,
        )
        self.yt = YoutubeReader(
            agent_name=self.agent_name,
            agent_config=self.agent.AGENT_CONFIG,
            collection_number=1,
            ApiClient=ApiClient,
            user=user,
        )
        self.stop_running_event = None
        self.browsed_links = []
        self.failures = 0
        self.user = user
        self.chain = Chain(user=user)
        self.cp = Prompts(user=user)
        self.ApiClient = ApiClient

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
        chain_name="",
        step_number=0,
        conversation_name="",
        vision_response: str = "",
        websearch: bool = False,
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
                    ApiClient=self.ApiClient,
                    user=self.user,
                ).get_memories(
                    user_input=user_input,
                    limit=3,
                    min_relevance_score=0.7,
                )
                negative_feedback = await WebsiteReader(
                    agent_name=self.agent_name,
                    agent_config=self.agent.AGENT_CONFIG,
                    collection_number=3,
                    ApiClient=self.ApiClient,
                    user=self.user,
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
                        ApiClient=self.ApiClient,
                        user=self.user,
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
                            ApiClient=self.ApiClient,
                            user=self.user,
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
        if vision_response != "":
            context += f"{self.agent_name}'s visual description from viewing uploaded images by user in this interaction:\n{vision_response}\n"
        if chain_name != "":
            try:
                for arg, value in kwargs.items():
                    if "{STEP" in value:
                        # get the response from the step number
                        step_response = self.chain.get_step_response(
                            chain_name=chain_name, step_number=step_number
                        )
                        # replace the {STEPx} with the response
                        value = value.replace(
                            f"{{STEP{step_number}}}",
                            step_response if step_response else "",
                        )
                        kwargs[arg] = value
            except:
                logging.info("No args to replace.")
            if "{STEP" in prompt:
                step_response = self.chain.get_step_response(
                    chain_name=chain_name, step_number=step_number
                )
                prompt = prompt.replace(
                    f"{{STEP{step_number}}}", step_response if step_response else ""
                )
            if "{STEP" in user_input:
                step_response = self.chain.get_step_response(
                    chain_name=chain_name, step_number=step_number
                )
                user_input = user_input.replace(
                    f"{{STEP{step_number}}}", step_response if step_response else ""
                )
        try:
            working_directory = self.agent.AGENT_CONFIG["settings"]["WORKING_DIRECTORY"]
        except:
            working_directory = "./WORKSPACE"
        helper_agent_name = self.agent_name
        if "helper_agent_name" not in kwargs:
            if "helper_agent_name" in self.agent.AGENT_CONFIG["settings"]:
                helper_agent_name = self.agent.AGENT_CONFIG["settings"][
                    "helper_agent_name"
                ]
        if "conversation_name" in kwargs:
            conversation_name = kwargs["conversation_name"]
        if conversation_name == "":
            conversation_name = f"{str(datetime.now())} Conversation"
        conversation = get_conversation(
            agent_name=self.agent_name,
            conversation_name=conversation_name,
            user=self.user,
        )
        if "conversation_results" in kwargs:
            conversation_results = int(kwargs["conversation_results"])
        else:
            conversation_results = int(top_results) if top_results > 0 else 5
        conversation_history = ""
        if "interactions" in conversation:
            if conversation["interactions"] != []:
                total_results = len(conversation["interactions"])
                # Get the last conversation_results interactions from the conversation
                new_conversation_history = []
                if total_results > conversation_results:
                    new_conversation_history = conversation["interactions"][
                        total_results - conversation_results : total_results
                    ]
                else:
                    new_conversation_history = conversation["interactions"]

                for interaction in new_conversation_history:
                    timestamp = (
                        interaction["timestamp"] if "timestamp" in interaction else ""
                    )
                    role = interaction["role"] if "role" in interaction else ""
                    message = interaction["message"] if "message" in interaction else ""
                    # Inject minimal conversation history into the prompt, just enough to give the agent some context.
                    # Strip code blocks out of the message
                    message = regex.sub(r"(```.*?```)", "", message)
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
        chain_name: str = "",
        step_number: int = 0,
        shots: int = 1,
        disable_memory: bool = True,
        conversation_name: str = "",
        browse_links: bool = False,
        persist_context_in_history: bool = False,
        images: list = [],
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
        if "websearch" in kwargs:
            websearch = True if str(kwargs["websearch"]).lower() == "true" else False
            del kwargs["websearch"]
        websearch_depth = 3
        if "websearch_depth" in kwargs:
            try:
                websearch_depth = int(kwargs["websearch_depth"])
            except:
                websearch_depth = 3
            del kwargs["websearch_depth"]
        if "conversation_name" in kwargs:
            conversation_name = kwargs["conversation_name"]
        if conversation_name == "":
            clean_datetime = re.sub(r"[^a-zA-Z0-9]", "", str(datetime.now()))
            conversation_name = f"{clean_datetime} Conversation"
        if "WEBSEARCH_TIMEOUT" in kwargs:
            try:
                websearch_timeout = int(kwargs["WEBSEARCH_TIMEOUT"])
            except:
                websearch_timeout = 0
        else:
            websearch_timeout = 0
        if browse_links != False:
            links = re.findall(r"(?P<url>https?://[^\s]+)", user_input)
            if links is not None and len(links) > 0:
                for link in links:
                    if (
                        link not in self.websearch.browsed_links
                        and link != ""
                        and link != None
                        and link != "None"
                    ):
                        logging.info(f"Browsing link: {link}")
                        self.websearch.browsed_links.append(link)
                        if str(link).startswith("https://www.youtube.com/watch?v="):
                            video_id = link.split("watch?v=")[1]
                            await self.yt.write_youtube_captions_to_memory(
                                video_id=video_id
                            )
                            link_list = None
                        else:
                            (
                                text_content,
                                link_list,
                            ) = await self.agent_memory.write_website_to_memory(
                                url=link
                            )
                        if int(websearch_depth) > 0:
                            if link_list is not None and len(link_list) > 0:
                                i = 0
                                for sublink in link_list:
                                    if sublink[1]:
                                        if (
                                            sublink[1]
                                            not in self.websearch.browsed_links
                                            and sublink[1] != ""
                                            and sublink[1] != None
                                            and sublink[1] != "None"
                                        ):
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
                try:
                    await self.websearch.websearch_agent(
                        user_input=search_string,
                        websearch_depth=websearch_depth,
                        websearch_timeout=websearch_timeout,
                    )
                except:
                    logging.warning("Failed to websearch.")
        vision_response = ""
        if "vision_provider" in self.agent.AGENT_CONFIG["settings"]:
            vision_provider = self.agent.AGENT_CONFIG["settings"]["vision_provider"]
            if (
                images != []
                and vision_provider != "None"
                and vision_provider != ""
                and vision_provider != None
            ):
                image_urls = []
                for image in images:
                    image_url = str(image).replace(
                        "./WORKSPACE/", f"{AGIXT_URI}/outputs/"
                    )
                    image_urls.append(image_url)
                logging.info(f"Getting vision response for images: {image_urls}")
                try:
                    vision_response = await self.agent.inference(
                        prompt=user_input, images=image_urls
                    )
                    logging.info(f"Vision Response: {vision_response}")
                except Exception as e:
                    logging.error(f"Error getting vision response: {e}")
                    logging.warning("Failed to get vision response.")
        formatted_prompt, unformatted_prompt, tokens = await self.format_prompt(
            user_input=user_input,
            top_results=int(context_results),
            prompt=prompt,
            prompt_category=prompt_category,
            chain_name=chain_name,
            step_number=step_number,
            conversation_name=conversation_name,
            websearch=websearch,
            vision_response=vision_response,
            **kwargs,
        )
        logging.info(f"Formatted Prompt: {formatted_prompt}")
        log_message = (
            user_input
            if user_input != "" and persist_context_in_history == False
            else formatted_prompt
        )
        log_interaction(
            agent_name=self.agent_name,
            conversation_name=conversation_name,
            role="USER",
            message=log_message,
            user=self.user,
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
            logging.error(f"{self.agent.PROVIDER} Error: {error}")
            logging.info(f"TOKENS: {tokens} PROMPT CONTENT: {formatted_prompt}")
            self.failures += 1
            if self.failures == 5:
                self.failures == 0
                logging.warning("Failed to get a response 5 times in a row.")
                return None
            logging.warning(f"Retrying in 10 seconds...")
            time.sleep(10)
            if context_results > 0:
                context_results = context_results - 1
            prompt_args = {
                "chain_name": chain_name,
                "step_number": step_number,
                "shots": shots,
                "disable_memory": disable_memory,
                "user_input": user_input,
                "context_results": context_results,
                "conversation_name": conversation_name,
                **kwargs,
            }
            return await self.run(
                prompt_name=prompt,
                prompt_category=prompt_category,
                **prompt_args,
            )
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
            if "![" in self.response:
                self.response = re.sub(
                    r"!\[.*?\]\(.*?\)", "", self.response, flags=re.DOTALL
                )
            tts = True
            if "tts" in kwargs:
                tts = str(kwargs["tts"]).lower() == "true"
            if "tts_provider" in agent_settings and tts:
                if (
                    agent_settings["tts_provider"] != "None"
                    and agent_settings["tts_provider"] != ""
                    and agent_settings["tts_provider"] != None
                ):
                    try:
                        tts_response = await self.agent.text_to_speech(
                            text=self.response
                        )
                        if not str(tts_response).startswith("http"):
                            file_type = "wav"
                            file_name = f"{uuid.uuid4().hex}.{file_type}"
                            audio_path = f"./WORKSPACE/{file_name}"
                            audio_data = base64.b64decode(tts_response)
                            with open(audio_path, "wb") as f:
                                f.write(audio_data)
                            tts_response = f'<audio controls><source src="{AGIXT_URI}/outputs/{file_name}" type="audio/wav"></audio>'
                        self.response = f"{self.response}\n\n{tts_response}"
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
                    img_gen_prompt = f"Users message: {user_input} \n\n{'The user uploaded an image, one does not need generated unless the user is specifically asking.' if images else ''} **The assistant is acting as sentiment analysis expert and only responds with a concise YES or NO answer on if the user would like an image as visual or a picture generated. No other explanation is needed!**\nWould the user potentially like an image generated based on their message?\nAssistant: "
                    create_img = await self.agent.inference(prompt=img_gen_prompt)
                    create_img = str(create_img).lower()
                    logging.info(f"Image Generation Decision Response: {create_img}")
                    if "yes" in create_img or "es," in create_img:
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
                            self.response = f"{self.response}\n\n![Image generated by {self.agent_name}]({generated_image})"
                        except:
                            logging.warning(
                                f"Failed to generate image for prompt: {image_generation_prompt}"
                            )
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
                prompt_args = {
                    "chain_name": chain_name,
                    "step_number": step_number,
                    "user_input": user_input,
                    "context_results": context_results,
                    "conversation_name": conversation_name,
                    "disable_memory": disable_memory,
                    **kwargs,
                }
                shot_response = await self.run(
                    agent_name=self.agent_name,
                    prompt_name=prompt,
                    prompt_category=prompt_category,
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
        command_list = [
            available_command["friendly_name"]
            for available_command in self.agent.available_commands
            if available_command["enabled"] == True
        ]
        if len(command_list) > 0:
            commands_to_execute = re.findall(r"#execute\((.*?)\)", self.response)
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
                        logging.info(f"Agent command list: {command_list}")
                        logging.info(f"Command to execute: {command_name}")
                        if command_name in command_list:
                            # Check if the command is a valid command in the self.agent.available_commands list
                            try:
                                if (
                                    str(self.agent.AUTONOMOUS_EXECUTION).lower()
                                    == "true"
                                ):
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
                                f"#execute({command_name}, {command_args})",
                                command_output,
                            )
                            if reformatted_response != self.response:
                                self.response = reformatted_response
