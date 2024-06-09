from Interactions import Interactions
from ApiClient import get_api_client, Conversations, Prompts, Chain
from readers.file import FileReader
from Extensions import Extensions
from pydub import AudioSegment
from Globals import getenv, get_tokens, DEFAULT_SETTINGS
from Models import ChatCompletions
from datetime import datetime
from typing import Type, get_args, get_origin, Union, List
from enum import Enum
from pydantic import BaseModel
import logging
import asyncio
import os
import base64
import uuid
import requests
import json
import time


class AGiXT:
    def __init__(self, user: str, agent_name: str, api_key: str):
        self.user_email = user.lower()
        self.api_key = api_key
        self.agent_name = agent_name
        self.uri = getenv("AGIXT_URI")
        self.ApiClient = get_api_client(api_key)
        self.agent_interactions = Interactions(
            agent_name=self.agent_name, user=self.user_email, ApiClient=self.ApiClient
        )
        self.agent = self.agent_interactions.agent
        self.agent_settings = (
            self.agent.AGENT_CONFIG["settings"]
            if "settings" in self.agent.AGENT_CONFIG
            else DEFAULT_SETTINGS
        )
        self.chain = Chain(user=self.user_email)
        self.agent_id = str(self.agent.get_agent_id())
        self.agent_workspace = os.path.join(os.getcwd(), "WORKSPACE", self.agent_id)
        os.makedirs(self.agent_workspace, exist_ok=True)
        self.outputs = f"{self.uri}/outputs/{self.agent_id}"

    async def prompts(self, prompt_category: str = "Default"):
        """
        Get a list of available prompts

        Args:
            prompt_category (str): Category of the prompt

        Returns:
            list: List of available prompts
        """
        return Prompts(user=self.user_email).get_prompts(
            prompt_category=prompt_category
        )

    async def chains(self):
        """
        Get a list of available chains

        Returns:
            list: List of available chains
        """
        return self.chain.get_chains()

    async def settings(self):
        """
        Get the agent settings

        Returns:
            dict: Agent settings
        """
        return self.agent_settings

    async def commands(self):
        """
        Get a list of available commands

        Returns:
            list: List of available commands
        """
        return self.agent.available_commands()

    async def browsed_links(self):
        """
        Get a list of browsed links

        Returns:
            list: List of browsed links
        """
        return self.agent.get_browsed_links()

    async def memories(
        self,
        user_input: str = "",
        limit_per_collection: int = 5,
        minimum_relevance_score: float = 0.3,
        additional_collection_number: int = 0,
    ):
        """
        Get a list of memories

        Args:
            user_input (str): User input to the agent
            limit_per_collection (int): Number of memories to return per collection
            minimum_relevance_score (float): Minimum relevance score for memories
            additional_collection_number (int): Additional collection number to pull memories from. Collections 0-5 are injected automatically.

        Returns:
            str: Agents relevant memories from the user input from collections 0-5 and the additional collection number if provided
        """
        formatted_prompt, prompt, tokens = await self.agent_interactions.format_prompt(
            user_input=user_input if user_input else "*",
            top_results=limit_per_collection,
            min_relevance_score=minimum_relevance_score,
            inject_memories_from_collection_number=int(additional_collection_number),
        )
        return formatted_prompt

    async def inference(
        self,
        user_input: str,
        prompt_category: str = "Default",
        prompt_name: str = "Custom Input",
        conversation_name: str = "",
        images: list = [],
        injected_memories: int = 5,
        shots: int = 1,
        browse_links: bool = False,
        voice_response: bool = False,
        log_user_input: bool = True,
        **kwargs,
    ):
        """
        Run inference on the AGiXT agent

        Args:
            user_input (str): User input to the agent
            prompt_category (str): Category of the prompt
            prompt_name (str): Name of the prompt to use
            injected_memories (int): Number of memories to inject into the conversation
            conversation_name (str): Name of the conversation
            browse_links (bool): Whether to browse links in the response
            images (list): List of image file paths
            shots (int): Number of responses to generate
            **kwargs: Additional keyword arguments

        Returns:
            str: Response from the agent
        """
        return await self.agent_interactions.run(
            user_input=user_input,
            prompt_category=prompt_category,
            prompt_name=prompt_name,
            context_results=injected_memories,
            shots=shots,
            conversation_name=conversation_name,
            browse_links=browse_links,
            images=images,
            tts=voice_response,
            log_user_input=log_user_input,
            **kwargs,
        )

    async def generate_image(self, prompt: str, conversation_name: str = ""):
        """
        Generate an image from a prompt

        Args:
            prompt (str): Prompt for the image generation

        Returns:
            str: URL of the generated image
        """
        if conversation_name != "" and conversation_name != None:
            c = Conversations(
                conversation_name=conversation_name,
                user=self.user_email,
            )
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Generating image.",
            )
        return await self.agent.generate_image(prompt=prompt)

    async def text_to_speech(self, text: str, conversation_name: str = ""):
        """
        Generate Text to Speech audio from text

        Args:
            text (str): Text to convert to speech

        Returns:
            str: URL of the generated audio
        """
        if conversation_name != "" and conversation_name != None:
            c = Conversations(conversation_name=conversation_name, user=self.user_email)
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Generating audio.",
            )
        tts_url = await self.agent.text_to_speech(text=text.text)
        if not str(tts_url).startswith("http"):
            file_type = "wav"
            file_name = f"{uuid.uuid4().hex}.{file_type}"
            audio_path = os.path.join(self.agent_workspace, file_name)
            full_path = os.path.normpath(os.path.join(self.agent_workspace, file_name))
            if not full_path.startswith(self.agent_workspace):
                raise Exception("Path given not allowed")
            audio_data = base64.b64decode(tts_url)
            with open(audio_path, "wb") as f:
                f.write(audio_data)
            tts_url = f"{self.outputs}/{file_name}"
        return tts_url

    async def audio_to_text(self, audio_path: str, conversation_name: str = ""):
        """
        Audio to Text transcription

        Args:
            audio_path (str): Path to the audio file

        Returns
            str: Transcription of the audio
        """
        if conversation_name != "" and conversation_name != None:
            c = Conversations(conversation_name=conversation_name, user=self.user_email)
            c.log_interaction(
                role=self.agent_name,
                message=f"Transcribing audio.",
            )
        response = await self.agent.transcribe_audio(audio_path=audio_path)
        return response

    async def translate_audio(self, audio_path: str, conversation_name: str = ""):
        """
        Translate an audio file

        Args:
            audio_path (str): Path to the audio file

        Returns
            str: Translation of the audio
        """
        if conversation_name != "" and conversation_name != None:
            c = Conversations(conversation_name=conversation_name, user=self.user_email)
            c.log_interaction(
                role=self.agent_name,
                message=f"Translating audio.",
            )
        response = await self.agent.translate_audio(audio_path=audio_path)
        return response

    async def execute_command(
        self,
        command_name: str,
        command_args: dict,
        conversation_name: str = "",
        voice_response: bool = False,
    ):
        """
        Execute a command with arguments

        Args:
            command_name (str): Name of the command to execute
            command_args (dict): Arguments for the command
            conversation_name (str): Name of the conversation
            voice_response (bool): Whether to generate a voice response

        Returns:
            str: Response from the command
        """
        if conversation_name != "" and conversation_name != None:
            c = Conversations(conversation_name=conversation_name, user=self.user_email)
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Executing command: {command_name} with args: {command_args}",
            )
        response = await Extensions(
            agent_name=self.agent_name,
            agent_config=self.agent.AGENT_CONFIG,
            conversation_name=conversation_name,
            ApiClient=self.ApiClient,
            api_key=self.api_key,
            user=self.user_email,
        ).execute_command(
            command_name=command_name,
            command_args=command_args,
        )
        if "tts_provider" in self.agent_settings and voice_response:
            if (
                self.agent_settings["tts_provider"] != "None"
                and self.agent_settings["tts_provider"] != ""
                and self.agent_settings["tts_provider"] != None
            ):
                tts_response = await self.text_to_speech(text=response)
                response = f"{response}\n\n{tts_response}"
        return response

    async def run_chain_step(
        self,
        chain_run_id=None,
        step: dict = {},
        chain_name="",
        user_input="",
        agent_override="",
        chain_args={},
        conversation_name="",
    ):
        if not chain_run_id:
            chain_run_id = await self.chain.get_chain_run_id(chain_name=chain_name)
        if step:
            if "prompt_type" in step:
                c = None
                if conversation_name != "":
                    c = Conversations(
                        conversation_name=conversation_name,
                        user=self.user_email,
                    )
                if agent_override != "":
                    agent_name = agent_override
                else:
                    agent_name = step["agent_name"]
                prompt_type = step["prompt_type"]
                step_number = step["step"]
                if "prompt_name" in step["prompt"]:
                    prompt_name = step["prompt"]["prompt_name"]
                else:
                    prompt_name = ""
                args = self.chain.get_step_content(
                    chain_run_id=chain_run_id,
                    chain_name=chain_name,
                    prompt_content=step["prompt"],
                    user_input=user_input,
                    agent_name=agent_name,
                )
                if chain_args != {}:
                    for arg, value in chain_args.items():
                        args[arg] = value
                if "chain_name" in args:
                    args["chain"] = args["chain_name"]
                if "chain" not in args:
                    args["chain"] = chain_name
                if "conversation_name" not in args:
                    args["conversation_name"] = f"Chain Execution History: {chain_name}"
                if "conversation" in args:
                    args["conversation_name"] = args["conversation"]
                if prompt_type == "Command":
                    if conversation_name != "" and conversation_name != None:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[ACTIVITY] Executing command: {step['prompt']['command_name']} with args: {args}",
                        )
                    result = await self.execute_command(
                        command_name=step["prompt"]["command_name"],
                        command_args=args,
                        conversation_name=args["conversation_name"],
                        voice_response=False,
                    )
                elif prompt_type == "Prompt":
                    if conversation_name != "" and conversation_name != None:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[ACTIVITY] Running prompt: {prompt_name} with args: {args}",
                        )
                    if "prompt_name" not in args:
                        args["prompt_name"] = prompt_name
                    result = await self.inference(
                        agent_name=agent_name,
                        user_input=user_input,
                        log_user_input=False,
                        **args,
                    )
                elif prompt_type == "Chain":
                    if conversation_name != "" and conversation_name != None:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[ACTIVITY] Running chain: {args['chain']} with args: {args}",
                        )
                    result = await self.execute_chain(
                        chain_name=args["chain"],
                        user_input=args["input"],
                        agent_override=agent_name,
                        from_step=args["from_step"] if "from_step" in args else 1,
                        chain_args=(
                            args["chain_args"]
                            if "chain_args" in args
                            else {"conversation_name": args["conversation_name"]}
                        ),
                        conversation_name=args["conversation_name"],
                        log_user_input=False,
                        voice_response=False,
                    )
        if result:
            if isinstance(result, dict) and "response" in result:
                result = result["response"]
            if result == "Unable to retrieve data.":
                result = None
            if isinstance(result, dict):
                result = json.dumps(result)
            if not isinstance(result, str):
                result = str(result)
            await self.chain.update_step_response(
                chain_run_id=chain_run_id,
                chain_name=chain_name,
                step_number=step_number,
                response=result,
            )
            return result
        else:
            return None

    async def execute_chain(
        self,
        chain_name,
        chain_run_id=None,
        user_input=None,
        agent_override="",
        from_step=1,
        chain_args={},
        log_user_input=False,
        conversation_name="",
        voice_response=False,
    ):
        chain_data = self.chain.get_chain(chain_name=chain_name)
        chain_dependencies = self.chain.get_chain_step_dependencies(
            chain_name=chain_name
        )

        async def check_dependencies_met(dependencies):
            for dependency in dependencies:
                try:
                    step_responses = self.chain.get_step_response(
                        chain_name=chain_name,
                        chain_run_id=chain_run_id,
                        step_number=int(dependency),
                    )
                except:
                    return False
                if not step_responses:
                    return False
            return True

        if not chain_run_id:
            chain_run_id = await self.chain.get_chain_run_id(chain_name=chain_name)
        if chain_data == {}:
            return f"Chain `{chain_name}` not found."
        c = Conversations(
            conversation_name=conversation_name,
            user=self.user_email,
        )
        if log_user_input:
            c.log_interaction(
                role="USER",
                message=user_input,
            )
        agent_name = agent_override if agent_override != "" else "AGiXT"
        if conversation_name != "":
            c.log_interaction(
                role=agent_name,
                message=f"[ACTIVITY] Running chain `{chain_name}`.",
            )
        response = ""
        tasks = []
        step_responses = []
        for step_data in chain_data["steps"]:
            if int(step_data["step"]) >= int(from_step):
                if "prompt" in step_data and "step" in step_data:
                    step = {}
                    step["agent_name"] = (
                        agent_override
                        if agent_override != ""
                        else step_data["agent_name"]
                    )
                    step["prompt_type"] = step_data["prompt_type"]
                    step["prompt"] = step_data["prompt"]
                    step["step"] = step_data["step"]
                    # Get the step dependencies from chain_dependencies then check if the dependencies are
                    # met before running the step
                    step_dependencies = chain_dependencies[str(step["step"])]
                    dependencies_met = await check_dependencies_met(step_dependencies)
                    while not dependencies_met:
                        await asyncio.sleep(1)
                        if step_responses == []:
                            step_responses = await asyncio.gather(*tasks)
                        else:
                            step_responses += await asyncio.gather(*tasks)
                        dependencies_met = await check_dependencies_met(
                            step_dependencies
                        )
                    task = asyncio.create_task(
                        self.run_chain_step(
                            chain_run_id=chain_run_id,
                            step=step,
                            chain_name=chain_name,
                            user_input=user_input,
                            agent_override=agent_override,
                            chain_args=chain_args,
                            conversation_name=conversation_name,
                        )
                    )
                    tasks.append(task)
        step_responses = await asyncio.gather(*tasks)
        logging.info(f"Step responses: {step_responses}")
        if step_responses:
            response = step_responses[-1]
        if response == None:
            return f"Chain failed to complete, it failed on step {step_data['step']}. You can resume by starting the chain from the step that failed with chain ID {chain_run_id}."
        if conversation_name != "":
            c.log_interaction(
                role=agent_name,
                message=response,
            )
        if "tts_provider" in self.agent_settings and voice_response:
            if (
                self.agent_settings["tts_provider"] != "None"
                and self.agent_settings["tts_provider"] != ""
                and self.agent_settings["tts_provider"] != None
            ):
                tts_response = await self.text_to_speech(text=response)
                response = f'{response}\n\n<audio controls><source src="{tts_response}" type="audio/wav"></audio>'
        c.log_interaction(role=self.agent_name, message=response)
        return response

    async def learn_from_websites(
        self,
        urls: list = [],
        scrape_depth: int = 3,
        summarize_content: bool = False,
        conversation_name: str = "",
    ):
        """
        Scrape a website and summarize the content

        Args:
            urls (list): List of URLs to scrape
            scrape_depth (int): Depth to scrape each URL
            summarize_content (bool): Whether to summarize the content
            conversation_name (str): Name of the conversation

        Returns:
            str: Agent response with a list of scraped links
        """
        if isinstance(urls, str):
            user_input = f"Learn from the information from this website:\n {urls} "
        else:
            url_str = {"\n".join(urls)}
            user_input = f"Learn from the information from these websites:\n {url_str} "
        response = await self.agent_interactions.websearch.scrape_websites(
            user_input=user_input,
            search_depth=scrape_depth,
            summarize_content=summarize_content,
            conversation_name=conversation_name,
        )
        return "I have read the information from the websites into my memory."

    async def learn_from_file(
        self,
        file_url: str = "",
        file_name: str = "",
        user_input: str = "",
        collection_number: int = 1,
        conversation_name: str = "",
    ):
        """
        Learn from a file

        Args:
            file_url (str): URL of the file
            file_path (str): Path to the file
            collection_number (int): Collection number to store the file
            conversation_name (str): Name of the conversation

        Returns:
            str: Response from the agent
        """
        if file_name == "":
            file_name = file_url.split("/")[-1]
        if file_url.startswith(self.outputs):
            file_path = os.path.join(self.agent_workspace, file_name)
        else:
            file_data = await self.download_file_to_workspace(
                url=file_url, file_name=file_name
            )
            file_name = file_data["file_name"]
            file_path = os.path.join(self.agent_workspace, file_name)
        if conversation_name != "" and conversation_name != None:
            c = Conversations(conversation_name=conversation_name, user=self.user_email)
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Reading file {file_name} into memory.",
            )
        if user_input == "":
            user_input = "Describe each stage of this image."
        file_type = file_name.split(".")[-1]
        file_reader = FileReader(
            agent_name=self.agent_name,
            agent_config=self.agent.AGENT_CONFIG,
            collection_number=collection_number,
            ApiClient=self.ApiClient,
            user=self.user_email,
        )
        if (
            file_type == "wav"
            or file_type == "mp3"
            or file_type == "ogg"
            or file_type == "m4a"
            or file_type == "flac"
            or file_type == "wma"
            or file_type == "aac"
        ):
            audio = AudioSegment.from_file(file_path)
            audio.export(file_path, format="wav")
            if conversation_name != "" and conversation_name != None:
                c.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY] Transcribing audio file `{file_name}` into memory.",
                )
            audio_response = await self.audio_to_text(audio_path=file_path)
            await file_reader.write_text_to_memory(
                user_input=user_input,
                text=f"Transcription from the audio file called `{file_name}`:\n{audio_response}\n",
                external_source=f"Audio file called `{file_name}`",
            )
            response = (
                f"I have transcribed the audio from `{file_name}` into my memory."
            )
        # If it is an image, generate a description then save to memory
        elif file_type in [
            "jpg",
            "jpeg",
            "png",
            "gif",
            "webp",
            "tiff",
            "bmp",
            "svg",
        ]:
            if "vision_provider" in self.agent.AGENT_CONFIG["settings"]:
                vision_provider = self.agent.AGENT_CONFIG["settings"]["vision_provider"]
                if (
                    vision_provider != "None"
                    and vision_provider != ""
                    and vision_provider != None
                ):
                    if conversation_name != "" and conversation_name != None:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[ACTIVITY] Viewing image at {file_url}.",
                        )
                    try:
                        vision_response = await self.agent.inference(
                            prompt=user_input, images=[file_url]
                        )
                        await file_reader.write_text_to_memory(
                            user_input=user_input,
                            text=f"{self.agent_name}'s visual description from viewing uploaded image called `{file_name}`:\n{vision_response}\n",
                            external_source=f"Image called `{file_name}`",
                        )
                        response = f"I have generated a description of the image called `{file_name}` into my memory."
                    except Exception as e:
                        logging.error(f"Error getting vision response: {e}")
                        response = f"[ERROR] I was unable to view the image called `{file_name}`."
                else:
                    response = (
                        f"[ERROR] I was unable to view the image called `{file_name}`."
                    )
        else:
            if conversation_name != "" and conversation_name != None:
                c.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY] Reading file `{file_name}` into memory.",
                )
            res = await file_reader.write_file_to_memory(file_path=file_path)
            if res == True:
                response = f"I have read the entire content of the file called {file_name} into my memory."
            else:
                response = f"I was unable to read the file called {file_name}."
        if conversation_name != "" and conversation_name != None:
            c.log_interaction(
                role=self.agent_name,
                message=(
                    f"[ACTIVITY] {response}"
                    if "[ERROR]" not in response
                    else f"[ACTIVITY]{response}"
                ),
            )
        return response

    async def download_file_to_workspace(self, url: str, file_name: str = ""):
        """
        Download a file from a URL to the workspace

        Args:
            url (str): URL of the file
            file_name (str): Name of the file

        Returns:
            str: URL of the downloaded file
        """
        if url.startswith("data:"):
            file_type = url.split(",")[0].split("/")[1].split(";")[0]
        else:
            file_type = url.split(".")[-1]
        if not file_type:
            file_type = "txt"
        file_name = f"{uuid.uuid4().hex}.{file_type}" if file_name == "" else file_name
        file_name = "".join(c if c.isalnum() else "_" for c in file_name)
        file_extension = file_name.split("_")[-1]
        file_name = file_name.replace(f"_{file_extension}", f".{file_extension}")
        file_path = os.path.join(self.agent_workspace, file_name)
        full_path = os.path.normpath(os.path.join(self.agent_workspace, file_name))
        if not full_path.startswith(self.agent_workspace):
            raise Exception("Path given not allowed")
        if url.startswith("http"):
            return {"file_name": file_name, "file_url": url}
        else:
            file_type = url.split(",")[0].split("/")[1].split(";")[0]
            file_data = base64.b64decode(url.split(",")[1])
            full_path = os.path.normpath(os.path.join(self.agent_workspace, file_name))
            if not full_path.startswith(self.agent_workspace):
                raise Exception("Path given not allowed")
            with open(file_path, "wb") as f:
                f.write(file_data)
            url = f"{self.outputs}/{file_name}"
            return {"file_name": file_name, "file_url": url}

    async def chat_completions(self, prompt: ChatCompletions):
        """
        Generate an OpenAI style chat completion response with a ChatCompletion prompt

        Args:
            prompt (ChatCompletions): Chat completions prompt

        Returns:
            dict: Chat completion response
        """
        conversation_name = prompt.user
        urls = []
        files = []
        new_prompt = ""
        browse_links = True
        tts = False
        if "mode" in self.agent_settings:
            mode = self.agent_settings["mode"]
        else:
            mode = "prompt"
        if "prompt_name" in self.agent_settings:
            prompt_name = self.agent_settings["prompt_name"]
        else:
            prompt_name = "Chat"
        if "prompt_category" in self.agent_settings:
            prompt_category = self.agent_settings["prompt_category"]
        else:
            prompt_category = "Default"
        prompt_args = {}
        if "prompt_args" in self.agent_settings:
            prompt_args = (
                json.loads(self.agent_settings["prompt_args"])
                if isinstance(self.agent_settings["prompt_args"], str)
                else self.agent_settings["prompt_args"]
            )
        if "context_results" in self.agent_settings:
            context_results = int(self.agent_settings["context_results"])
        else:
            context_results = 5
        if "injected_memories" in self.agent_settings:
            context_results = int(self.agent_settings["injected_memories"])
        if "command_name" in self.agent_settings:
            command_name = self.agent_settings["command_name"]
        else:
            command_name = ""
        if "command_args" in self.agent_settings:
            command_args = (
                json.loads(self.agent_settings["command_args"])
                if isinstance(self.agent_settings["command_args"], str)
                else self.agent_settings["command_args"]
            )
        else:
            command_args = {}
        if "command_variable" in self.agent_settings:
            command_variable = self.agent_settings["command_variable"]
        else:
            command_variable = "text"
        if "chain_name" in self.agent_settings:
            chain_name = self.agent_settings["chain_name"]
        else:
            chain_name = ""
        if "chain_args" in self.agent_settings:
            chain_args = (
                json.loads(self.agent_settings["chain_args"])
                if isinstance(self.agent_settings["chain_args"], str)
                else self.agent_settings["chain_args"]
            )
        else:
            chain_args = {}
        if "tts_provider" in self.agent_settings:
            tts_provider = str(self.agent_settings["tts_provider"]).lower()
            if tts_provider != "none" and tts_provider != "":
                tts = True
        for message in prompt.messages:
            if "mode" in message:
                if message["mode"] in ["prompt", "command", "chain"]:
                    mode = message["mode"]
            if "injected_memories" in message:
                context_results = int(message["injected_memories"])
            if "prompt_category" in message:
                prompt_category = message["prompt_category"]
            if "prompt_name" in message:
                prompt_name = message["prompt_name"]
            if "prompt_args" in message:
                prompt_args = (
                    json.loads(message["prompt_args"])
                    if isinstance(message["prompt_args"], str)
                    else message["prompt_args"]
                )
            if "command_name" in message:
                command_name = message["command_name"]
            if "command_args" in message:
                command_args = (
                    json.loads(message["command_args"])
                    if isinstance(message["command_args"], str)
                    else message["command_args"]
                )
            if "command_variable" in message:
                command_variable = message["command_variable"]
            if "chain_name" in message:
                chain_name = message["chain_name"]
            if "chain_args" in message:
                chain_args = (
                    json.loads(message["chain_args"])
                    if isinstance(message["chain_args"], str)
                    else message["chain_args"]
                )
            if "browse_links" in message:
                browse_links = str(message["browse_links"]).lower() == "true"
            if "tts" in message:
                tts = str(message["tts"]).lower() == "true"
            if "content" not in message:
                continue
            if isinstance(message["content"], str):
                role = message["role"] if "role" in message else "User"
                if role.lower() == "system":
                    if "/" in message["content"]:
                        new_prompt += f"{message['content']}\n\n"
                if role.lower() == "user":
                    new_prompt += f"{message['content']}\n\n"
            if isinstance(message["content"], list):
                for msg in message["content"]:
                    if "text" in msg:
                        role = message["role"] if "role" in message else "User"
                        if role.lower() == "user":
                            new_prompt += f"{msg['text']}\n\n"
                    # Iterate over the msg to find _url in one of the keys then use the value of that key unless it has a "url" under it
                    if isinstance(msg, dict):
                        for key, value in msg.items():
                            if "_url" in key:
                                url = str(value["url"] if "url" in value else value)
                                if "file_name" in msg:
                                    file_name = str(msg["file_name"])
                                else:
                                    file_name = ""
                                if key != "audio_url":
                                    files.append(
                                        await self.download_file_to_workspace(
                                            url=url, file_name=file_name
                                        )
                                    )
                                else:
                                    # If there is an audio_url, it is the user's voice input that needs transcribed before running inference
                                    audio_file_info = (
                                        await self.download_file_to_workspace(url=url)
                                    )
                                    full_path = os.path.normpath(
                                        os.path.join(
                                            self.agent_workspace,
                                            audio_file_info["file_name"],
                                        )
                                    )
                                    if not full_path.startswith(self.agent_workspace):
                                        raise Exception("Path given not allowed")
                                    audio_file_path = os.path.join(
                                        self.agent_workspace,
                                        audio_file_info["file_name"],
                                    )
                                    if url.startswith(self.agent_workspace):
                                        wav_file = os.path.join(
                                            self.agent_workspace,
                                            f"{uuid.uuid4().hex}.wav",
                                        )
                                        AudioSegment.from_file(
                                            audio_file_path
                                        ).set_frame_rate(16000).export(
                                            wav_file, format="wav"
                                        )
                                        transcribed_audio = await self.audio_to_text(
                                            audio_path=wav_file,
                                            conversation_name=conversation_name,
                                        )
                                        new_prompt += transcribed_audio
            # Add user input to conversation
            c = Conversations(conversation_name=conversation_name, user=self.user_email)
            c.log_interaction(role="USER", message=new_prompt)
            for file in files:
                await self.learn_from_file(
                    file_url=file["file_url"],
                    file_name=file["file_name"],
                    user_input=new_prompt,
                    collection_number=1,
                    conversation_name=conversation_name,
                )
            await self.learn_from_websites(
                urls=urls,
                scrape_depth=3,
                summarize_content=False,
                conversation_name=conversation_name,
            )
            if mode == "command" and command_name and command_variable:
                try:
                    command_args = (
                        json.loads(self.agent_settings["command_args"])
                        if isinstance(self.agent_settings["command_args"], str)
                        else self.agent_settings["command_args"]
                    )
                except Exception as e:
                    command_args = {}
                command_args[self.agent_settings["command_variable"]] = new_prompt
                response = await self.execute_command(
                    command_name=self.agent_settings["command_name"],
                    command_args=command_args,
                    conversation_name=conversation_name,
                    voice_response=tts,
                )
            elif mode == "chain" and chain_name:
                chain_name = self.agent_settings["chain_name"]
                try:
                    chain_args = (
                        json.loads(self.agent_settings["chain_args"])
                        if isinstance(self.agent_settings["chain_args"], str)
                        else self.agent_settings["chain_args"]
                    )
                except Exception as e:
                    chain_args = {}
                response = await self.execute_chain(
                    chain_name=chain_name,
                    user_input=new_prompt,
                    agent_override=self.agent_name,
                    chain_args=chain_args,
                    log_user_input=False,
                    conversation_name=conversation_name,
                    voice_response=tts,
                )
            elif mode == "prompt":
                response = await self.inference(
                    user_input=new_prompt,
                    prompt_name=prompt_name,
                    prompt_category=prompt_category,
                    conversation_name=conversation_name,
                    injected_memories=context_results,
                    shots=prompt.n,
                    browse_links=browse_links,
                    voice_response=tts,
                    log_user_input=False,
                    **prompt_args,
                )
        prompt_tokens = get_tokens(new_prompt)
        completion_tokens = get_tokens(response)
        total_tokens = int(prompt_tokens) + int(completion_tokens)
        res_model = {
            "id": conversation_name,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.agent_name,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": str(response),
                    },
                    "finish_reason": "stop",
                    "logprobs": None,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }
        return res_model

    async def batch_inference(
        self,
        user_inputs: List[str] = [],
        prompt_category: str = "Default",
        prompt_name: str = "Ask Questions",
        conversation_name: str = "",
        images: list = [],
        injected_memories: int = 5,
        batch_size: int = 10,
        browse_links: bool = False,
        voice_response: bool = False,
        log_user_input: bool = False,
        **kwargs,
    ):
        i = 0
        tasks = []
        responses = []
        if user_inputs == []:
            return []
        for user_input in user_inputs:
            i += 1
            if i % batch_size == 0:
                responses += await asyncio.gather(**tasks)
                tasks = []
            task = asyncio.create_task(
                await self.inference(
                    user_input=user_input,
                    prompt_category=prompt_category,
                    prompt_name=prompt_name,
                    conversation_name=conversation_name,
                    images=images,
                    injected_memories=injected_memories,
                    browse_links=browse_links,
                    voice_response=voice_response,
                    log_user_input=log_user_input,
                    **kwargs,
                )
            )
            tasks.append(task)
        responses += await asyncio.gather(**tasks)
        return responses

    async def dpo(
        self,
        question: str = "",
        injected_memories: int = 10,
    ):
        context_async = self.memories(
            user_input=question,
            limit_per_collection=injected_memories,
        )
        chosen_async = self.inference(
            user_input=question,
            prompt_category="Default",
            prompt_name="Answer Question with Memory",
            injected_memories=injected_memories,
            log_user_input=False,
        )
        rejected_async = self.inference(
            user_input=question,
            prompt_category="Default",
            prompt_name="Wrong Answers Only",
            log_user_input=False,
        )
        chosen = await chosen_async
        rejected = await rejected_async
        context = await context_async
        prompt = f"### Context\n{context}\n### Question\n{question}"
        return prompt, chosen, rejected

    # Creates a synthetic dataset from memories in sharegpt format
    async def create_dataset_from_memories(self, batch_size: int = 10):
        self.agent_settings["training"] = True
        self.agent_interactions.agent.update_agent_config(
            new_config=self.agent_settings, config_key="settings"
        )
        memories = []
        questions = []
        dataset_name = f"{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}-DPO-Dataset"
        collections = await self.agent_interactions.agent_memory.get_collections()
        for collection in collections:
            self.collection_name = collection
            memories += (
                await self.agent_interactions.agent_memory.export_collection_to_json()
            )
        logging.info(f"There are {len(memories)} memories.")
        memories = [memory["text"] for memory in memories]
        # Get a list of questions about each memory
        question_list = self.batch_inference(
            user_inputs=memories,
            batch_size=batch_size,
            prompt_category="Default",
            prompt_name="Ask Questions",
        )
        for question in question_list:
            # Convert the response to a list of questions
            question = question.split("\n")
            question = [
                item.lstrip("0123456789.*- ") for item in question if item.lstrip()
            ]
            question = [item for item in question if item]
            question = [item.lstrip("0123456789.*- ") for item in question]
            questions += question
        prompts = []
        good_answers = []
        bad_answers = []
        for question in questions:
            prompt, chosen, rejected = await self.dpo(
                question=question,
                injected_memories=10,
            )
            prompts.append(prompt)
            good_answers.append(
                [
                    {"content": prompt, "role": "user"},
                    {"content": chosen, "role": "assistant"},
                ]
            )
            bad_answers.append(
                [
                    {"content": prompt, "role": "user"},
                    {"content": rejected, "role": "assistant"},
                ]
            )
        dpo_dataset = {
            "prompt": questions,
            "chosen": good_answers,
            "rejected": bad_answers,
        }
        # Save messages to a json file to be used as a dataset
        agent_id = self.agent_interactions.agent.get_agent_id()
        dataset_dir = os.path.join(self.agent_workspace, "datasets")

        os.makedirs(dataset_dir, exist_ok=True)
        dataset_name = "".join(
            [c for c in dataset_name if c.isalpha() or c.isdigit() or c == " "]
        )
        dataset_filename = f"{dataset_name}.json"
        full_path = os.path.normpath(
            os.path.join(self.agent_workspace, dataset_filename)
        )
        if not full_path.startswith(self.agent_workspace):
            raise Exception("Path given not allowed")
        with open(os.path.join(dataset_dir, dataset_filename), "w") as f:
            f.write(json.dumps(dpo_dataset))
        self.agent_settings["training"] = False
        self.agent_interactions.agent.update_agent_config(
            new_config=self.agent_settings, config_key="settings"
        )
        return dpo_dataset

    def convert_to_pydantic_model(
        self,
        input_string: str,
        model: Type[BaseModel],
        max_failures: int = 3,
        response_type: str = None,
        **kwargs,
    ):
        input_string = str(input_string)
        fields = model.__annotations__
        field_descriptions = []
        for field, field_type in fields.items():
            description = f"{field}: {field_type}"
            if get_origin(field_type) == Union:
                field_type = get_args(field_type)[0]
            if isinstance(field_type, type) and issubclass(field_type, Enum):
                enum_values = ", ".join([f"{e.name} = {e.value}" for e in field_type])
                description += f" (Enum values: {enum_values})"
            field_descriptions.append(description)
        schema = "\n".join(field_descriptions)
        response = self.inference(
            user_input=input_string,
            schema=schema,
            prompt_category="Default",
            prompt_name="Convert to Pydantic Model",
            log_user_input=False,
        )
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].strip()
        try:
            response = json.loads(response)
            if response_type == "json":
                return response
            else:
                return model(**response)
        except Exception as e:
            if "failures" in kwargs:
                failures = int(kwargs["failures"]) + 1
                if failures > max_failures:
                    logging.error(
                        f"Error: {e} . Failed to convert the response to the model after 3 attempts. Response: {response}"
                    )
                    return (
                        response
                        if response
                        else "Failed to convert the response to the model."
                    )
            else:
                failures = 1
            logging.warning(
                f"Error: {e} . Failed to convert the response to the model, trying again. {failures}/3 failures. Response: {response}"
            )
            return self.convert_to_pydantic_model(
                input_string=input_string,
                model=model,
                max_failures=max_failures,
                response_type=response_type,
                failures=failures,
            )
