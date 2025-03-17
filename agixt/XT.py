from Interactions import Interactions
from ApiClient import get_api_client, Conversations, Prompts, Chain
from Memories import Memories
from Extensions import Extensions
from pydub import AudioSegment
from Globals import getenv, get_tokens, DEFAULT_SETTINGS
from Models import ChatCompletions, TasksToDo, ChainCommandName, TranslationRequest
from datetime import datetime
from typing import (
    List,
    Type,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)
from MagicalAuth import MagicalAuth
from enum import Enum
from pydantic import BaseModel
import pdfplumber
import docx2txt
import zipfile
import pandas as pd
import subprocess
import logging
import asyncio
import requests
import inspect
import base64
import uuid
import json
import time
import os
import re


class AGiXT:
    def __init__(
        self,
        user: str,
        agent_name: str,
        api_key: str,
        conversation_name: str = None,
        collection_id=None,
    ):
        self.user_email = user.lower()
        if api_key is not None:
            api_key = str(api_key).replace("Bearer ", "").replace("bearer ", "")
        self.api_key = api_key
        self.auth = MagicalAuth(token=api_key)
        self.conversation = None
        self.conversation_id = None
        self.conversation_name = None
        if conversation_name != None:
            self.conversation = Conversations(
                conversation_name=conversation_name, user=self.user_email
            )
            self.conversation_id = self.conversation.get_conversation_id()
            self.conversation_name = conversation_name
        self.agent_name = agent_name
        self.uri = getenv("AGIXT_URI")
        if collection_id is not None:
            self.collection_id = str(collection_id)
        elif conversation_name:
            self.collection_id = self.conversation_id
        else:
            self.collection_id = "0"
        if self.conversation_name is None:
            self.conversation_name = datetime.now().strftime("%Y-%m-%d")
            self.conversation = Conversations(
                conversation_name=self.conversation_name, user=self.user_email
            )
            self.conversation_id = self.conversation.get_conversation_id()
        self.ApiClient = get_api_client(api_key)
        self.agent_interactions = Interactions(
            agent_name=self.agent_name,
            user=self.user_email,
            ApiClient=self.ApiClient,
            collection_id=self.collection_id,
        )
        self.agent = self.agent_interactions.agent
        self.agent_settings = (
            self.agent.AGENT_CONFIG["settings"]
            if "settings" in self.agent.AGENT_CONFIG
            else DEFAULT_SETTINGS
        )
        self.chain = Chain(user=self.user_email)
        self.agent_workspace = self.agent.working_directory
        os.makedirs(self.agent_workspace, exist_ok=True)
        self.conversation_workspace = os.path.join(
            self.agent_workspace, self.conversation_id
        )
        os.makedirs(self.conversation_workspace, exist_ok=True)
        self.outputs = f"{self.uri}/outputs/{self.agent.agent_id}"
        self.failures = 0
        self.input_tokens = 0
        self.file_reader = None
        if self.collection_id is not None:
            self.file_reader = Memories(
                agent_name=self.agent_name,
                agent_config=self.agent.AGENT_CONFIG,
                collection_number=self.collection_id,
                ApiClient=self.ApiClient,
                user=self.user_email,
            )

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
        additional_collection: str = "0",
    ):
        """
        Get a list of memories

        Args:
            user_input (str): User input to the agent
            limit_per_collection (int): Number of memories to return per collection
            minimum_relevance_score (float): Minimum relevance score for memories
            additional_collection (int): Additional collection number to pull memories from. Collections 0-5 are injected automatically.

        Returns:
            str: Agents relevant memories from the user input from collections 0-5 and the additional collection number if provided
        """
        formatted_prompt, prompt, tokens = await self.agent_interactions.format_prompt(
            user_input=user_input if user_input else "*",
            top_results=limit_per_collection,
            min_relevance_score=minimum_relevance_score,
            inject_memories_from_collection_number=additional_collection,
        )
        return formatted_prompt

    async def inference(
        self,
        user_input: str,
        prompt_category: str = "Default",
        prompt_name: str = "Custom Input",
        images: list = [],
        injected_memories: int = 100,
        conversation_results: int = 15,
        shots: int = 1,
        browse_links: bool = False,
        voice_response: bool = False,
        log_user_input: bool = True,
        log_output: bool = True,
        language: str = "en",
        **kwargs,
    ):
        """
        Run inference on the AGiXT agent

        Args:
            user_input (str): User input to the agent
            prompt_category (str): Category of the prompt
            prompt_name (str): Name of the prompt to use
            injected_memories (int): Number of memories to inject into the conversation
            conversation_results (int): Number of interactions to inject into the conversation
            browse_links (bool): Whether to browse links in the response
            images (list): List of image file paths
            shots (int): Number of responses to generate
            voice_response (bool): Whether to generate a voice response
            log_user_input (bool): Whether to log the user input
            log_output (bool): Whether to log the output
            language (str): Language of the response
            **kwargs: Additional keyword arguments

        Returns:
            str: Response from the agent
        """
        if "conversation_results" in kwargs:
            try:
                conversation_results = int(kwargs["conversation_results"])
            except:
                conversation_results = 10
            del kwargs["conversation_results"]
        if "context_results" in kwargs:
            try:
                injected_memories = int(kwargs["context_results"])
            except:
                injected_memories = 100
            del kwargs["context_results"]
        if "tts" in kwargs:
            voice_response = str(kwargs["tts"]).lower() == "true"
            del kwargs["tts"]
        if "conversation_name" in kwargs:
            del kwargs["conversation_name"]
        response = await self.agent_interactions.run(
            user_input=user_input,
            prompt_category=prompt_category,
            prompt_name=prompt_name,
            context_results=injected_memories,
            conversation_results=conversation_results,
            shots=shots,
            conversation_name=self.conversation_name,
            browse_links=browse_links,
            images=images,
            tts=voice_response,
            log_user_input=log_user_input,
            log_output=log_output,
            **kwargs,
        )
        if language == "en":
            return response
        translation_prompt = f"Markdown output is acceptable in the `target_language_translated_text` field, but all output should only be in the target language aside from that variable name. The goal is to intuitively and effectively translate the full given text from English to {language}. **Text to translate to target language '{language}'**:\n"
        target_language_user_input = await self.convert_to_model(
            input_string=f"{translation_prompt}{user_input}",
            model=TranslationRequest,
        )
        self.conversation.log_interaction(
            role="USER",
            message=f"{user_input}\n**Translated to {language.upper()}**\n{target_language_user_input.target_language_translated_text}",
        )
        if voice_response:
            await self.text_to_speech(
                text=target_language_user_input.target_language_translated_text,
                log_output=True,
            )
        stripped_response = re.sub(r"```[^```]+```", "", response)
        target_language_response = await self.convert_to_model(
            input_string=f"{translation_prompt}{stripped_response}",
            model=TranslationRequest,
        )
        new_response = f"{response}\n**Translated to {language.upper()}**\n{target_language_response.target_language_translated_text}"
        self.conversation.log_interaction(
            role=self.agent_name,
            message=new_response,
        )
        if voice_response:
            await self.text_to_speech(
                text=target_language_response.target_language_translated_text,
                log_output=True,
            )
        return new_response

    async def generate_image(self, prompt: str):
        """
        Generate an image from a prompt

        Args:
            prompt (str): Prompt for the image generation

        Returns:
            str: URL of the generated image
        """
        self.conversation.log_interaction(
            role=self.agent_name,
            message=f"[ACTIVITY] Generating image.",
        )
        return await self.agent.generate_image(prompt=prompt)

    async def text_to_speech(
        self,
        text: str,
        log_output: bool = False,
    ):
        """
        Generate Text to Speech audio from text

        Args:
            text (str): Text to convert to speech
            log_output (bool): Whether to log the output

        Returns:
            str: URL of the generated audio
        """
        tts_url = await self.agent.text_to_speech(text=text)
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
        if log_output:
            if tts_url.endswith(".mp3"):
                self.conversation.log_interaction(
                    role=self.agent_name,
                    message=f'<audio controls><source src="{tts_url}" type="audio/mpeg"></audio>',
                )
            else:
                self.conversation.log_interaction(
                    role=self.agent_name,
                    message=f'<audio controls><source src="{tts_url}" type="audio/wav"></audio>',
                )
        return tts_url

    async def audio_to_text(self, audio_path: str):
        """
        Audio to Text transcription

        Args:
            audio_path (str): Path to the audio file

        Returns
            str: Transcription of the audio
        """
        self.conversation.log_interaction(
            role=self.agent_name,
            message=f"[ACTIVITY] Transcribing recorded audio.",
        )
        # Start a timer
        start = time.time()
        response = await self.agent.transcribe_audio(audio_path=audio_path)
        # End the timer
        end = time.time()
        elapsed_time = end - start
        elapsed_time = "{:.2f}".format(elapsed_time)
        self.conversation.log_interaction(
            role=self.agent_name,
            message=f"Transcribed audio in {elapsed_time} seconds.",
        )
        return response

    async def translate_audio(self, audio_path: str):
        """
        Translate an audio file

        Args:
            audio_path (str): Path to the audio file

        Returns
            str: Translation of the audio
        """
        self.conversation.log_interaction(
            role=self.agent_name,
            message=f"[ACTIVITY] Translating audio.",
        )
        response = await self.agent.translate_audio(audio_path=audio_path)
        return response

    async def execute_command(
        self,
        command_name: str,
        command_args: dict,
        voice_response: bool = False,
        log_output: bool = False,
        log_activities: bool = False,
    ):
        """
        Execute a command with arguments

        Args:
            command_name (str): Name of the command to execute
            command_args (dict): Arguments for the command
            voice_response (bool): Whether to generate a voice response
            log_output (bool): Whether to log the output
            log_activities (bool): Whether to log the activities

        Returns:
            str: Response from the command
        """
        if log_activities:
            self.conversation.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Executing command `{command_name}` with args:\n```json\n{json.dumps(command_args, indent=2)}```",
            )
        try:
            response = await Extensions(
                agent_name=self.agent_name,
                agent_id=self.agent.agent_id,
                agent_config=self.agent.AGENT_CONFIG,
                conversation_name=self.conversation_name,
                conversation_id=self.conversation_id,
                ApiClient=self.ApiClient,
                api_key=self.api_key,
                user=self.user_email,
            ).execute_command(
                command_name=command_name,
                command_args=command_args,
            )
        except Exception as e:
            logging.error(f"Error executing command: {e}")
            response = f"Error executing command `{command_name}`."
        if "tts_provider" in self.agent_settings and voice_response:
            if (
                self.agent_settings["tts_provider"] != "None"
                and self.agent_settings["tts_provider"] != ""
                and self.agent_settings["tts_provider"] != None
            ):
                await self.text_to_speech(
                    text=response,
                    log_output=log_output,
                )
        if log_output:
            self.conversation.log_interaction(role=self.agent_name, message=response)
        return response

    async def run_chain_step(
        self,
        chain_run_id=None,
        step: dict = {},
        chain_name="",
        user_input="",
        agent_override="",
        chain_args={},
    ):
        if not chain_run_id:
            chain_run_id = await self.chain.get_chain_run_id(chain_name=chain_name)
        if step:
            if "prompt_type" in step:
                if agent_override != "":
                    agent_name = agent_override
                else:
                    agent_name = (
                        step["agent_name"] if "agent_name" in step else self.agent_name
                    )
                prompt_type = str(step["prompt_type"]).lower()
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
                if prompt_type == "command":
                    self.conversation.log_interaction(
                        role=self.agent_name,
                        message=f"[ACTIVITY] Executing command `{step['prompt']['command_name']}` with args:\n```json\n{json.dumps(args, indent=2)}```",
                    )
                    result = await self.execute_command(
                        command_name=step["prompt"]["command_name"],
                        command_args=args,
                        voice_response=False,
                    )
                elif prompt_type == "prompt":
                    self.conversation.log_interaction(
                        role=self.agent_name,
                        message=f"[ACTIVITY] Running prompt: `{prompt_name}` with args:\n```json\n{json.dumps(args, indent=2)}```",
                    )
                    if prompt_name != "":
                        if "browse_links" not in args:
                            args["browse_links"] = False
                        args["prompt_name"] = prompt_name
                        args["log_user_input"] = False
                        args["voice_response"] = False
                        args["log_output"] = False
                        args["user_input"] = user_input
                        result = self.ApiClient.prompt_agent(
                            agent_name=agent_name,
                            prompt_name=prompt_name,
                            prompt_args=args,
                        )
                elif prompt_type == "chain":
                    self.conversation.log_interaction(
                        role=self.agent_name,
                        message=f"[ACTIVITY] Running chain: `{args['chain']}` with args:\n```json\n{json.dumps(args, indent=2)}```",
                    )
                    if "chain_name" in args:
                        args["chain"] = args["chain_name"]
                    if "user_input" in args:
                        args["input"] = args["user_input"]
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
        voice_response=False,
    ):
        chain_data = self.chain.get_chain(chain_name=chain_name)
        if not chain_run_id:
            chain_run_id = await self.chain.get_chain_run_id(chain_name=chain_name)
        if chain_data == {}:
            return f"Chain `{chain_name}` not found."
        if log_user_input:
            self.conversation.log_interaction(
                role="USER",
                message=user_input,
            )
        self.conversation.log_interaction(
            role=self.agent_name,
            message=f"[ACTIVITY] Running chain `{chain_name}`.",
        )
        response = ""
        step_responses = []
        logging.info(f"Chain data: {chain_data}")
        if "steps" not in chain_data:
            return f"Chain `{chain_name}` has no steps."
        if len(chain_data["steps"]) == 0:
            return f"Chain `{chain_name}` has no steps."
        for step_data in chain_data["steps"]:
            if int(step_data["step"]) >= int(from_step):
                if "prompt" in step_data and "step" in step_data:
                    step = {}
                    if "agent_name" not in step_data:
                        step_data["agent_name"] = self.agent_name
                    step["agent_name"] = (
                        agent_override
                        if agent_override != ""
                        else step_data["agent_name"]
                    )
                    step["prompt_type"] = step_data["prompt_type"]
                    step["prompt"] = step_data["prompt"]
                    step["step"] = step_data["step"]
                    task = await self.run_chain_step(
                        chain_run_id=chain_run_id,
                        step=step,
                        chain_name=chain_name,
                        user_input=user_input,
                        agent_override=agent_override,
                        chain_args=chain_args,
                    )
                    step_responses.append(task)
        logging.info(f"Step responses: {step_responses}")
        if step_responses:
            response = step_responses[-1]
        if response == None:
            return f"Chain failed to complete, it failed on step {step_data['step']}. You can resume by starting the chain from the step that failed with chain ID {chain_run_id}."
        self.conversation.log_interaction(role=self.agent_name, message=response)
        if "tts_provider" in self.agent_settings and voice_response:
            if (
                self.agent_settings["tts_provider"] != "None"
                and self.agent_settings["tts_provider"] != ""
                and self.agent_settings["tts_provider"] != None
            ):
                await self.text_to_speech(text=response, log_output=True)
        return response

    async def learn_from_websites(
        self,
        urls: list = [],
        summarize_content: bool = False,
    ):
        """
        Scrape a website and summarize the content

        Args:
            urls (list): List of URLs to scrape
            scrape_depth (int): Depth to scrape each URL
            summarize_content (bool): Whether to summarize the content

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
            summarize_content=summarize_content,
            conversation_name=self.conversation_name,
        )
        return "I have read the information from the websites into my memory."

    async def learn_spreadsheet(self, user_input, file_path):
        file_name = os.path.basename(file_path)
        file_type = str(file_name).split(".")[-1]
        string_file_content = ""
        thinking_id = self.conversation.get_thinking_id(agent_name=self.agent_name)
        try:
            if file_type.lower() == "csv":
                df = pd.read_csv(file_path)
                csv = df.to_csv(index=False)
                string_file_content += f"Content from file uploaded named `{file_name}`:\n```csv\n{csv}```\n"
                return (
                    f"Read [{file_name}]({file_path}) into memory.",
                    string_file_content,
                )
            else:  # Excel file
                try:
                    xl = pd.ExcelFile(file_path)
                    if len(xl.sheet_names) > 1:
                        sheet_count = len(xl.sheet_names)
                        for i, sheet_name in enumerate(xl.sheet_names, 1):
                            df = xl.parse(sheet_name)
                            csv_file_path = file_path.replace(
                                f".{file_type}", f"_{i}.csv"
                            )
                            csv_file_name = os.path.basename(csv_file_path)
                            self.conversation.log_interaction(
                                role=self.agent_name,
                                message=f"[ACTIVITY] ({i}/{sheet_count}) Converted sheet `{sheet_name}` in `{file_name}` to CSV file `{csv_file_name}`.",
                            )
                            df.to_csv(csv_file_path, index=False)
                            message, file_content = await self.learn_spreadsheet(
                                user_input=user_input,
                                file_path=csv_file_path,
                            )
                            self.conversation.log_interaction(
                                role=self.agent_name, message=f"[ACTIVITY] {message}"
                            )
                            string_file_content += file_content
                        return (
                            f"Processed all sheets in [{file_name}]({file_path}).",
                            string_file_content,
                        )
                    else:
                        df = pd.read_excel(file_path)
                        csv = df.to_csv(index=False)
                        string_file_content += f"Content from file uploaded named `{file_name}`:\n```csv\n{csv}```\n"
                        return (
                            f"Read [{file_name}]({file_path}) into memory.",
                            string_file_content,
                        )
                except Exception as e:
                    self.conversation.log_interaction(
                        role=self.agent_name,
                        message=f"[ACTIVITY][ERROR] Failed to read Excel file `{file_name}`: {str(e)}",
                    )
                    return (
                        f"Failed to read [{file_name}]({file_path}). Error: {str(e)}",
                        "",
                    )
        except Exception as e:
            logging.error(f"Unexpected error processing spreadsheet: {e}")
            return f"Failed to process [{file_name}]({file_path}). Unexpected error: {str(e)}"

    async def learn_from_file(
        self,
        file_url: str = "",
        file_name: str = "",
        user_input: str = "",
        collection_id: str = "0",
    ):
        """
        Learn from a file

        Args:
            file_url (str): URL of the file
            file_name (str): Name of the file
            user_input (str): User input to the agent
            collection_id (str): Collection ID to save the file to

        Returns:
            str: Response from the agent
        """
        file_content = ""
        if file_name == "":
            file_name = file_url.split("/")[-1]
        if file_url.startswith(self.outputs):
            folder_path = file_url.split(f"{self.outputs}/")[1]
            file_path = os.path.normpath(
                os.path.join(self.agent_workspace, folder_path)
            )
        else:
            logging.info(f"{file_url} does not start with {self.outputs}")
            file_data = await self.download_file_to_workspace(
                url=file_url, file_name=file_name
            )
            self.conversation.increment_attachment_count()
            if file_data == {}:
                self.conversation.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY][ERROR] I was unable to read the file from {file_url}.",
                )
                return f"Unable to read the file from {file_url} ."
            file_name = file_data["file_name"]
            file_path = os.path.normpath(
                os.path.join(self.agent_workspace, collection_id, file_name)
            )
        logging.info(f"File path: {file_path}")
        if not file_path.startswith(self.agent_workspace):
            file_path = os.path.normpath(
                os.path.join(self.agent_workspace, collection_id, file_name)
            )
            logging.info(f"Corrected file path: {file_path}")
        file_type = file_name.split(".")[-1]
        if file_type not in ["jpg", "jpeg", "png", "gif"]:
            self.conversation.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Reading [{file_name}]({file_url}) into memory.",
            )
        if file_type in ["ppt", "pptx"]:
            # Convert it to a PDF
            pdf_file_path = file_path.replace(".pptx", ".pdf").replace(".ppt", ".pdf")
            file_name = str(file_name).replace(".pptx", ".pdf").replace(".ppt", ".pdf")
            self.conversation.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Converting PowerPoint file [{file_name}]({file_url}) to PDF.",
            )
            try:
                result = subprocess.run(
                    [
                        "libreoffice",
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        os.path.dirname(file_path),
                        file_path,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,
                )
                if result.returncode != 0:
                    raise Exception(
                        f"Conversion failed: {result.stderr.decode('utf-8', errors='ignore')}"
                    )
            except Exception as e:
                logging.error(f"Error converting PowerPoint to PDF: {e}")
                return f"Failed to convert PowerPoint file [{file_name}]({file_url}) to PDF. Error: {str(e)}"
            file_path = pdf_file_path
            file_type = "pdf"
        if user_input == "":
            user_input = "Describe each stage of this image."
        disallowed_types = ["exe", "bin", "rar"]
        if file_type in disallowed_types:
            response = f"[ERROR] I was unable to read the file called `{file_name}`."
        elif file_type == "pdf":
            file_content += f"Content from PDF uploaded named `{file_name}`:\n"
            with pdfplumber.open(file_path) as pdf:
                content = "\n".join([page.extract_text() for page in pdf.pages])
                file_content += content
            if "pdf_vision" in self.agent_settings:
                if (
                    self.agent_settings["pdf_vision"] != "None"
                    and self.agent_settings["pdf_vision"] != ""
                    and self.agent_settings["pdf_vision"] != None
                    and str(self.agent_settings["pdf_vision"]).lower() != "false"
                    and self.agent_settings["vision_provider"] != "None"
                    and self.agent_settings["vision_provider"] != ""
                    and self.agent_settings["vision_provider"] != None
                ):
                    with pdfplumber.open(file_path) as pdf:
                        for i, page in enumerate(pdf.pages):
                            page_image = page.to_image(width=256, height=256)
                            image_path = (
                                f"{file_path.replace('.pdf', f'_page_{i}.png')}"
                            )
                            page_image.save(image_path)
                            vision_response = await self.agent.vision_inference(
                                prompt=content, images=[image_path]
                            )
                        file_content += f"Visual description from viewing uploaded PDF called `{file_name}` from page {i} with OCR:\n"
                        file_content += vision_response
            self.input_tokens += get_tokens(content)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await self.file_reader.write_text_to_memory(
                user_input=user_input,
                text=f"Content from PDF uploaded at {timestamp} named `{file_name}`:\n{content}",
                external_source=f"file {file_path}",
            )
            response = f"Read [{file_name}]({file_url}) into memory."
        elif file_path.endswith(".zip"):
            extracted_zip_folder_name = f"extracted_{file_name.replace('.zip', '_zip')}"
            new_folder = os.path.normpath(
                os.path.join(
                    self.agent_workspace, collection_id, extracted_zip_folder_name
                )
            )
            file_content += f"Content from the zip file uploaded named `{file_name}`:\n"
            if new_folder.startswith(self.agent_workspace):
                with zipfile.ZipFile(file_path, "r") as zipObj:
                    zipObj.extractall(path=new_folder)
                # Iterate over every file that was extracted including subdirectories
                for root, dirs, files in os.walk(new_folder):
                    for name in files:
                        current_folder = root.replace(new_folder, "")
                        output_url = f"{self.outputs}/{collection_id}/{extracted_zip_folder_name}/{current_folder}/{name}"
                        logging.info(f"Output URL: {output_url}")
                        file_content += f"Content from file uploaded named `{name}`:\n"
                        file_content += await self.learn_from_file(
                            file_url=output_url,
                            file_name=name,
                            user_input=user_input,
                            collection_id=collection_id,
                        )
                response = f"Extracted the content of the zip file [{file_name}]({file_url}) and read them into memory."
            else:
                response = (
                    f"[ERROR] I was unable to read the file called `{file_name}`."
                )
        elif file_path.endswith(".doc") or file_path.endswith(".docx"):
            content = docx2txt.process(file_path)
            docx_content = (
                f"Content from the document uploaded named `{file_name}`:\n{content}"
            )
            file_content += docx_content
            self.input_tokens += get_tokens(content)
            await self.file_reader.write_text_to_memory(
                user_input=user_input,
                text=docx_content,
                external_source=f"file {file_path}",
            )
            response = f"Read [{file_name}]({file_url}) into memory."
        elif file_type == "xlsx" or file_type == "xls" or file_type == "csv":
            response, content = await self.learn_spreadsheet(
                user_input=user_input,
                file_path=file_path,
            )
            file_content += content
            await self.file_reader.write_text_to_memory(
                user_input=user_input,
                text=content,
                external_source=f"file {file_path}",
            )
        elif (
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
            self.conversation.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Transcribing audio file [{file_name}]({file_url}) into memory.",
            )
            audio_response = await self.audio_to_text(audio_path=file_path)
            file_content += (
                f"Transcription from the audio file uploaded named `{file_name}`:\n"
            )
            file_content += audio_response
            self.input_tokens += get_tokens(audio_response)
            await self.file_reader.write_text_to_memory(
                user_input=user_input,
                text=f"Transcription from the audio file called `{file_name}`:\n{audio_response}\n",
                external_source=f"audio {file_name}",
            )
            response = (
                f"Transcribed the audio from [{file_name}]({file_url}) into memory."
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
            if (
                self.agent.VISION_PROVIDER != "None"
                and self.agent.VISION_PROVIDER != ""
                and self.agent.VISION_PROVIDER != None
            ):
                self.conversation.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY] Uploaded `{file_name}` ![Uploaded {file_name}]({file_url})",
                )
                try:
                    vision_prompt = f"The assistant has an image in context\nThe user's last message was: {user_input}\nThe uploaded image is `{file_name}`.\n\nAnswer anything relevant to the image that the user is questioning if anything, additionally, describe the image in detail."
                    self.input_tokens += get_tokens(vision_prompt)
                    vision_response = await self.agent.vision_inference(
                        prompt=vision_prompt, images=[file_url]
                    )
                    file_content += f"Visual description from viewing uploaded image called `{file_name}`:\n"
                    file_content += vision_response
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    await self.file_reader.write_text_to_memory(
                        user_input=user_input,
                        text=f"{self.agent_name}'s visual description from viewing uploaded image called `{file_name}` from {timestamp}:\n{vision_response}\n",
                        external_source=f"image {file_name}",
                    )
                    response = f"Read [{file_name}]({file_url}) into memory."
                except Exception as e:
                    logging.error(f"Error getting vision response: {e}")
                    response = (
                        f"[ERROR] I was unable to view the image called `{file_name}`."
                    )
            else:
                response = (
                    f"[ERROR] I was unable to view the image called `{file_name}`."
                )
        else:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fp = os.path.normpath(file_path)
            if fp.startswith(self.agent_workspace):
                try:
                    with open(fp, "r") as f:
                        content = f.read()
                except:
                    with open(fp, "rb") as f:
                        content = f.read()
                    content = base64.b64encode(content).decode("utf-8")
                file_content += (
                    f"Content from file uploaded named `{file_name}` at {timestamp}:\n"
                )
                file_content += content
                self.input_tokens += get_tokens(content)
                # Check how many lines are in the file content
                lines = content.split("\n")
                if len(lines) > 1:
                    for line_number, line in enumerate(lines):
                        await self.file_reader.write_text_to_memory(
                            user_input=user_input,
                            text=f"Content from file uploaded named `{file_name}` at {timestamp} on line number {line_number + 1}:\n{line}",
                            external_source=f"file {fp}",
                        )
                else:
                    await self.file_reader.write_text_to_memory(
                        user_input=user_input,
                        text=f"Content from file uploaded named `{file_name}` at {timestamp}:\n{content}",
                        external_source=f"file {fp}",
                    )
                response = f"Read [{file_name}]({file_url}) into memory."
            else:
                response = (
                    f"[ERROR] I was unable to read the file called `{file_name}`."
                )
        self.conversation.log_interaction(
            role=self.agent_name,
            message=(
                f"[ACTIVITY] {response}"
                if "[ERROR]" not in response
                else f"[ACTIVITY]{response}"
            ),
        )
        return file_content

    async def download_file_to_workspace(
        self, url: str, file_name: str = "", download_headers={}
    ):
        """
        Download a file from a URL to the workspace

        Args:
            url (str): URL of the file
            file_name (str): Name of the file

        Returns:
            str: URL of the downloaded file
        """
        logging.info(f"Downloading file from {url}")
        if url.startswith("data:"):
            file_type = url.split(",")[0].split("/")[1].split(";")[0]
        else:
            if "?" in url:
                file_type = url.split("?")[0]
                file_type = file_type.split(".")[-1]
            else:
                file_type = url.split(".")[-1]
        if not file_type:
            file_type = "txt"
        self.conversation_id
        if not self.conversation_id:
            self.conversation_id = self.conversation.get_conversation_id()
        file_name = f"{uuid.uuid4().hex}.{file_type}" if file_name == "" else file_name
        file_name = "".join(c if c.isalnum() else "_" for c in file_name)
        file_extension = file_name.split("_")[-1]
        file_name = file_name.replace(f"_{file_extension}", f".{file_extension}")
        full_path = os.path.normpath(
            os.path.join(self.conversation_workspace, file_name)
        )
        logging.info(f"Full path to download file to: {full_path}")
        if not full_path.startswith(self.conversation_workspace):
            raise Exception("Path given not allowed")
        if "," in url:
            file_type = url.split(",")[0].split("/")[1].split(";")[0]
            file_data = base64.b64decode(url.split(",")[1])
        else:
            file_type = file_name.split(".")[-1]
            # Download the file
            try:
                if not url.startswith("http"):
                    return {}
                if url in ["", None]:
                    return {}
                file_download = requests.get(url)
                file_data = file_download.content
            except Exception as e:
                logging.error(f"Error downloading file: {e}")
                return {}
        full_path = os.path.normpath(
            os.path.join(self.conversation_workspace, file_name)
        )
        if not full_path.startswith(self.conversation_workspace):
            raise Exception("Path given not allowed")
        with open(full_path, "wb") as f:
            f.write(file_data)
        url = f"{self.outputs}/{self.conversation_id}/{file_name}"
        logging.info(f"Downloaded file available at {url}")
        return {"file_name": file_name, "file_url": url}

    async def plan_task(
        self,
        user_input: str,
        websearch: bool = False,
        websearch_depth: int = 3,
        log_user_input: bool = True,
        log_output: bool = True,
        enable_new_command: bool = True,
    ):
        """
        Plan a task from a user input, create and enable a new command to execute the plan

        Args:
        user_input (str): User input to the agent
        websearch (bool): Whether to include web research in the chain
        websearch_depth (int): Depth of web research to include
        log_user_input (bool): Whether to log the user input
        log_output (bool): Whether to log the output
        enable_new_command (bool): Whether to enable the new command for the agent

        Returns:
        str: The name of the created chain
        """
        if log_user_input:
            self.conversation.log_interaction(
                role="USER",
                message=user_input,
            )
        self.conversation.log_interaction(
            role=self.agent_name,
            message=f"[ACTIVITY] Determining primary objective.",
        )
        # Who is the expert here?
        # Run the prompt "Expert Determination" with the user input
        expert = await self.inference(
            user_input=user_input,
            prompt_category="Default",
            prompt_name="Expert Determination",
            log_output=False,
            log_user_input=False,
        )
        # Use the prompt "Prompt Generator" to generate a prompt for the user to provide the primary objective
        primary_objective = await self.inference(
            user_input=user_input,
            job_title=expert,
            task=user_input,
            prompt_name="Prompt Generator",
            log_output=False,
            log_user_input=False,
        )

        # primary_objective = Step 1, execute chain "Smart Prompt" with the user input to get Primary Objective
        chain_name = await self.inference(
            user_input=user_input,
            introduction=primary_objective,
            prompt_category="Default",
            prompt_name="Title a Chain",
            log_output=False,
            log_user_input=False,
        )
        chain_title = await self.convert_to_model(
            input_string=chain_name,
            model=ChainCommandName,
        )
        chain_name = chain_title.command_name
        self.conversation.log_interaction(
            role=self.agent_name,
            message=f"[ACTIVITY] Breaking objective into a list of tasks.",
        )
        # numbered_list_of_tasks = Step 2, Execute prompt "Break into Steps" with `introduction` being step 1 response, websearch true if researching
        # Note - Should do this more than once to get a better list of tasks
        numbered_list_of_tasks = await self.inference(
            user_input=user_input,
            introduction=primary_objective,
            prompt_category="Default",
            prompt_name="Break into Steps",
            websearch=websearch,
            websearch_depth=websearch_depth,
            injected_memories=100,
            log_output=False,
            log_user_input=False,
        )
        task_list = await self.convert_to_model(
            input_string=numbered_list_of_tasks,
            model=TasksToDo,
        )
        self.chain.add_chain(chain_name=chain_name)
        self.conversation.log_interaction(
            role=self.agent_name,
            message=f"[ACTIVITY] Creating new command `{chain_name}`.",
        )
        i = 1
        total_tasks = len(task_list.tasks)
        x = 1
        # First step in the chain should be to disable the command so that the agent doesn't try to execute it while executing it
        self.chain.add_chain_step(
            chain_name=chain_name,
            agent_name=self.agent_name,
            step_number=i,
            prompt_type="Command",
            prompt={
                "command_name": "Disable Command",
                "command_args": {
                    "agent_name": self.agent_name,
                    "command_name": chain_name,
                },
            },
        )
        i += 1
        for task in task_list.tasks:
            self.conversation.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Planning task `{x}` of `{total_tasks}`.",
            )
            x += 1
            # Create a smart prompt with the objective and task in context
            self.chain.add_chain_step(
                chain_name=chain_name,
                agent_name=self.agent_name,
                step_number=i,
                prompt_type="Chain",
                prompt={
                    "chain_name": "Smart Prompt",
                    "input": f"Primary Objective to keep in mind while working on the task: {primary_objective} \nThe only task to complete to move towards the objective: {task}",
                },
            )
            i += 1
            self.chain.add_chain_step(
                chain_name=chain_name,
                agent_name=self.agent_name,
                step_number=i,
                prompt_type="Chain",
                prompt={
                    "chain": (
                        "Smart Instruct"
                        if websearch
                        else "Smart Instruct - No Research"
                    ),
                    "input": "{STEP" + str(i - 1) + "}",
                },
            )
            i += 1
        list_of_tasks = "\n".join(
            [f"{i}. {task}" for i, task in enumerate(task_list.tasks, 1)]
        )
        # Enable the command of the chain name
        if enable_new_command:
            self.agent.update_agent_config(
                new_config={chain_name: True}, config_key="commands"
            )
            message = f"I have created a new command called `{chain_name}`. The tasks will be executed in the following order:\n{list_of_tasks}\n\nWould you like me to execute `{chain_name}` now?"
        else:
            message = f"I have created a new command called `{chain_name}`. The tasks will be executed in the following order:\n{list_of_tasks}\n\nIf you are able to enable the command, I can execute it for you. Alternatively, you can execute the command manually."
        if log_output:
            self.conversation.log_interaction(
                role=self.agent_name,
                message=message,
            )
        return {
            "chain_name": chain_name,
            "message": message,
            "tasks": list_of_tasks,
        }

    async def update_planned_task(
        self,
        chain_name: str,
        user_input: str,
        log_user_input: bool = True,
        log_output: bool = True,
        enable_new_command: bool = True,
    ):
        """
        Modify the chain based on user input

        Args:
        chain_name (str): Name of the chain to update
        user_input (str): User input to the agent
        log_user_input (bool): Whether to log the user input
        log_output (bool): Whether to log the output

        Returns:
        str: Response from the agent
        """
        # Basically just delete the old chain after we extract the tasks and then run the plan_task function with more input from the user.
        current_chain = self.chain.get_chain(chain_name=chain_name)
        # This function is still a work in progress
        # Need to

        self.chain.delete_chain(chain_name=chain_name)
        return await self.plan_task(
            user_input=user_input,
            log_user_input=log_user_input,
            log_output=log_output,
            enable_new_command=enable_new_command,
        )

    def remove_tagged_content(self, text: str, tag: str) -> str:
        """Safely remove content between tags without using regex."""
        start_tag = f"[{tag}]"
        end_tag = f"[/{tag}]"

        while True:
            start = text.find(start_tag)
            if start == -1:
                break
            end = text.find(end_tag, start)
            if end == -1:
                break
            text = text[:start] + text[end + len(end_tag) :]
        return text

    async def chat_completions(self, prompt: ChatCompletions):
        """
        Generate an OpenAI style chat completion response with a ChatCompletion prompt

        Args:
            prompt (ChatCompletions): Chat completions prompt

        Returns:
            dict: Chat completion response
        """
        # conversation_name = prompt.user
        c = self.conversation
        conversation_id = self.conversation_id
        urls = []
        files = []
        new_prompt = ""
        browse_links = True
        tts = False
        websearch = False
        language = "en"
        log_output = True
        log_user_input = True
        if "websearch" in self.agent_settings:
            websearch = str(self.agent_settings["websearch"]).lower() == "true"
        if "mode" in self.agent_settings:
            mode = self.agent_settings["mode"]
        else:
            mode = "prompt"
        if "prompt_name" in self.agent_settings:
            prompt_name = self.agent_settings["prompt_name"]
        else:
            prompt_name = "Think About It"
        if "prompt_category" in self.agent_settings:
            prompt_category = self.agent_settings["prompt_category"]
        else:
            prompt_category = "Default"
        if "LANGUAGE" in self.agent_settings:
            language = str(self.agent_settings["LANGUAGE"]).lower()
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
        if "conversation_results" in self.agent_settings:
            conversation_results = int(self.agent_settings["conversation_results"])
        else:
            conversation_results = 6
        if "command_name" in self.agent_settings:
            command_name = self.agent_settings["command_name"]
        else:
            command_name = ""
        if "command_args" in self.agent_settings:
            try:
                command_args = (
                    json.loads(self.agent_settings["command_args"])
                    if isinstance(self.agent_settings["command_args"], str)
                    else self.agent_settings["command_args"]
                )
            except Exception as e:
                command_args = {}
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
                if "tts" in self.agent_settings:
                    tts = str(self.agent_settings["tts"]).lower() == "true"
        analyze_user_input = False
        if "analyze_user_input" in self.agent_settings:
            analyze_user_input = (
                str(self.agent_settings["analyze_user_input"]).lower() == "true"
            )
        include_sources = False
        if "include_sources" in self.agent_settings:
            include_sources = (
                str(self.agent_settings["include_sources"]).lower() == "true"
            )
        for message in prompt.messages:
            if "mode" in message:
                if message["mode"] in ["prompt", "command", "chain"]:
                    mode = message["mode"]
            if "log_output" in message:
                log_output = str(message["log_output"]).lower() == "true"
            if "log_user_input" in message:
                log_user_input = str(message["log_user_input"]).lower() == "true"
            if "injected_memories" in message:
                context_results = int(message["injected_memories"])
            if "language" in message:
                language = message["language"]
            if "conversation_results" in message:
                conversation_results = int(message["conversation_results"])
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
            if "websearch" in message:
                websearch = str(message["websearch"]).lower() == "true"
            if "analyze_user_input" in message:
                analyze_user_input = (
                    str(message["analyze_user_input"]).lower() == "true"
                )
            if "include_sources" in message:
                include_sources = str(message["include_sources"]).lower() == "true"
            download_headers = {}
            if "download_headers" in message:
                download_headers = (
                    json.loads(message["download_headers"])
                    if isinstance(message["download_headers"], str)
                    else message["download_headers"]
                )
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
                                if url.startswith("https://github.com/"):
                                    do_not_pull_repo = [
                                        "/pull/",
                                        "/issues",
                                        "/discussions",
                                        "/actions/",
                                        "/projects",
                                        "/security",
                                        "/releases",
                                        "/commits",
                                        "/branches",
                                        "/tags",
                                        "/stargazers",
                                        "/watchers",
                                        "/network",
                                        "/settings",
                                        "/compare",
                                        "/archive",
                                    ]
                                    if any(x in url for x in do_not_pull_repo):
                                        # If the URL is not a repository, don't pull it
                                        urls.append(url)
                                    else:
                                        # Download the zip for the repo
                                        github_user = (
                                            self.agent_settings["GITHUB_USERNAME"]
                                            if "GITHUB_USERNAME" in self.agent_settings
                                            else None
                                        )
                                        github_token = (
                                            self.agent_settings["GITHUB_TOKEN"]
                                            if "GITHUB_TOKEN" in self.agent_settings
                                            else None
                                        )
                                        github_repo = url.replace(
                                            "https://github.com/", ""
                                        )
                                        github_repo = github_repo.replace(
                                            "https://www.github.com/", ""
                                        )
                                        if not github_branch:
                                            github_branch = "main"
                                        user = github_repo.split("/")[0]
                                        repo = github_repo.split("/")[1]
                                        if " " in repo:
                                            repo = repo.split(" ")[0]
                                        if "\n" in repo:
                                            repo = repo.split("\n")[0]
                                        # Remove any symbols that would not be in the user, repo, or branch
                                        for symbol in [
                                            " ",
                                            "\n",
                                            "\t",
                                            "\r",
                                            "\\",
                                            "/",
                                            ":",
                                            "*",
                                            "?",
                                            '"',
                                            "<",
                                            ">",
                                        ]:
                                            repo = repo.replace(symbol, "")
                                            user = user.replace(symbol, "")
                                            github_branch = github_branch.replace(
                                                symbol, ""
                                            )
                                        repo_url = f"https://github.com/{user}/{repo}/archive/refs/heads/{github_branch}.zip"
                                        try:
                                            if github_user and github_token:
                                                response = requests.get(
                                                    repo_url,
                                                    auth=(github_user, github_token),
                                                )
                                            else:
                                                response = requests.get(repo_url)
                                        except:
                                            github_branch = "master"
                                            repo_url = f"https://github.com/{user}/{repo}/archive/refs/heads/{github_branch}.zip"
                                            try:
                                                if github_user and github_token:
                                                    response = requests.get(
                                                        repo_url,
                                                        auth=(
                                                            github_user,
                                                            github_token,
                                                        ),
                                                    )
                                                else:
                                                    response = requests.get(repo_url)
                                            except:
                                                pass
                                        if response.status_code == 200:
                                            file_name = (
                                                f"{user}_{repo}_{github_branch}.zip"
                                            )
                                            file_data = response.content
                                            file_path = os.path.normpath(
                                                os.path.join(
                                                    self.agent_workspace,
                                                    conversation_id,
                                                    file_name,
                                                )
                                            )
                                            if file_path.startswith(
                                                self.agent_workspace
                                            ):
                                                with open(file_path, "wb") as f:
                                                    f.write(file_data)
                                                files.append(
                                                    {
                                                        "file_name": file_name,
                                                        "file_url": f"{self.outputs}/{conversation_id}/{file_name}",
                                                    }
                                                )
                                        else:
                                            urls.append(url)
                                if "file_name" in msg:
                                    file_name = str(msg["file_name"])
                                else:
                                    file_name = ""
                                if key != "audio_url":
                                    downloaded_file = (
                                        await self.download_file_to_workspace(
                                            url=url,
                                            file_name=file_name,
                                            download_headers=download_headers,
                                        )
                                    )
                                    if downloaded_file != {}:
                                        files.append(downloaded_file)
                                    else:
                                        c.log_interaction(
                                            role=self.agent_name,
                                            message=f"[SUBACTIVITY][{thinking_id}][ERROR] I was unable to read from the URL specified.",
                                        )
                                else:
                                    # If there is an audio_url, it is the user's voice input that needs transcribed before running inference
                                    audio_file_info = (
                                        await self.download_file_to_workspace(url=url)
                                    )
                                    full_path = os.path.normpath(
                                        os.path.join(
                                            self.agent_workspace,
                                            conversation_id,
                                            audio_file_info["file_name"],
                                        )
                                    )
                                    if not full_path.startswith(self.agent_workspace):
                                        raise Exception("Path given not allowed")
                                    audio_file_path = os.path.join(
                                        self.agent_workspace,
                                        conversation_id,
                                        audio_file_info["file_name"],
                                    )
                                    if os.path.normpath(audio_file_path).startswith(
                                        self.agent_workspace
                                    ):
                                        wav_file = os.path.join(
                                            self.agent_workspace,
                                            conversation_id,
                                            f"{uuid.uuid4().hex}.wav",
                                        )
                                        AudioSegment.from_file(
                                            audio_file_path
                                        ).set_frame_rate(16000).export(
                                            wav_file, format="wav"
                                        )
                                        transcribed_audio = await self.audio_to_text(
                                            audio_path=wav_file,
                                        )
                                        new_prompt += transcribed_audio
        # Add user input to conversation
        for file in files:
            new_prompt += f"\nUploaded file: `{file['file_name']}`."
        if "log_output" in prompt_args:
            log_output = str(prompt_args["log_output"]).lower() == "true"
            del prompt_args["log_output"]
        if "log_user_input" in prompt_args:
            log_user_input = str(prompt_args["log_user_input"]).lower() == "true"
            del prompt_args["log_user_input"]
        if log_user_input:
            c.log_interaction(role="USER", message=new_prompt)
        if log_output:
            thinking_id = c.get_thinking_id(agent_name=self.agent_name)
        file_contents = []
        current_input_tokens = get_tokens(new_prompt)
        for file in files:
            content = await self.learn_from_file(
                file_url=file["file_url"],
                file_name=file["file_name"],
                user_input=new_prompt,
                collection_id=self.conversation_id,
            )
            file_contents.append(content)
        if file_contents:
            file_content = "\n".join(file_contents)
            file_tokens = get_tokens(file_content)
            current_input_tokens = file_tokens + current_input_tokens
        else:
            file_content = ""
            current_input_tokens = self.input_tokens
        if "user_input" in prompt_args:
            del prompt_args["user_input"]
        if "prompt_name" in prompt_args:
            prompt_name = prompt_args["prompt_name"]
            del prompt_args["prompt_name"]
        if "prompt_category" in prompt_args:
            prompt_category = prompt_args["prompt_category"]
            del prompt_args["prompt_category"]
        if "websearch" in prompt_args:
            websearch = prompt_args["websearch"]
            del prompt_args["websearch"]
        if "browse_links" in prompt_args:
            browse_links = prompt_args["browse_links"]
            del prompt_args["browse_links"]
        if "tts" in prompt_args:
            tts = prompt_args["voice_response"]
            del prompt_args["tts"]
        if "context_results" in prompt_args:
            context_results = prompt_args["context_results"]
            del prompt_args["context_results"]
        if "conversation_results" in prompt_args:
            conversation_results = prompt_args["conversation_results"]
            del prompt_args["conversation_results"]
        if "analyze_user_input" in prompt_args:
            analyze_user_input = prompt_args["analyze_user_input"]
            del prompt_args["analyze_user_input"]
        if "voice_response" in prompt_args:
            tts = prompt_args["voice_response"]
            del prompt_args["voice_response"]
        if "injected_memories" in prompt_args:
            context_results = prompt_args["injected_memories"]
            del prompt_args["injected_memories"]
        if "shots" in prompt_args:
            del prompt_args["shots"]
        if "data_analysis" in prompt_args:
            del prompt_args["data_analysis"]

        await self.learn_from_websites(
            urls=urls,
            summarize_content=False,
        )
        data_analysis = ""
        if analyze_user_input:
            data_analysis = await self.analyze_data(user_input=new_prompt)
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
                voice_response=tts,
            )
        elif mode == "prompt":
            if current_input_tokens < self.agent.max_input_tokens:
                if file_content:
                    prompt_args["uploaded_file_data"] = file_content
            if len(language) > 2:
                language = language[:2]
            response = await self.inference(
                user_input=new_prompt,
                prompt_name=prompt_name,
                prompt_category=prompt_category,
                injected_memories=context_results,
                conversation_results=conversation_results,
                shots=prompt.n,
                websearch=websearch,
                browse_links=browse_links,
                voice_response=tts,
                log_user_input=False,
                log_output=False,
                data_analysis=data_analysis,
                language=language,
                include_sources=include_sources,
                **prompt_args,
            )
            if response.startswith(f"{self.agent_name}:"):
                response = response[len(f"{self.agent_name}:") :]
            if response.startswith(f"{self.agent_name} :"):
                response = response[len(f"{self.agent_name} :") :]
            thoughts_and_reflections = ""
            if "<answer>" in response:
                if "</answer>" not in response:
                    response += "</answer>"
                try:
                    thoughts_and_reflections = response.split("<answer>")[0]
                except:
                    thoughts_and_reflections = ""
                try:
                    after_thoughts = response.split("</answer>")[1]
                    if len(after_thoughts) > 10:
                        thoughts_and_reflections += after_thoughts
                except:
                    pass
                answer = response.split("<answer>")[-1]
                answer = answer.split("</answer>")[0]
                response = answer
            if log_output:
                if thoughts_and_reflections:
                    # Before logging the response, lets get all activities matching the `thinking_id` mermaid diagram
                    enable_mermaid = False
                    if "enable_mermaid" in self.agent_settings:
                        enable_mermaid = (
                            str(self.agent_settings["enable_mermaid"]).lower() == "true"
                        )
                    if enable_mermaid:
                        activities = c.get_subactivities(thinking_id)
                        if activities:
                            activity_prompt = f"{new_prompt}\n\n{activities}\n\nReview the detailed activities list and create a mermaid diagram that describes the paths taken during the detailed activities that were performed based on the user input. This mermaid diagram should start with ```mermaid\nContent of the diagram\n```\ninside of the <answer> block as the final response. The activities describe the thoughts in steps that ultimately led to the response from the assistant to the user based on the user input. Be as detailed as possible with the diagram. Ensure each item in the diagram is in quotes."
                            mermaid_diagram = await self.inference(
                                user_input=activity_prompt,
                                prompt_category="Default",
                                prompt_name="Think About It",
                                log_output=False,
                                log_user_input=False,
                                voice_response=False,
                                analyze_user_input=False,
                                browse_links=False,
                                websearch=False,
                                disable_commands=True,
                                conversation_name=self.conversation_name,
                            )
                            if mermaid_diagram:
                                mermaid_diagram = mermaid_diagram.split("<answer>")[
                                    -1
                                ].split("</answer>")[0]
                                c.log_interaction(
                                    role=self.agent_name,
                                    message=f"[SUBACTIVITY][{thinking_id}][DIAGRAM] Generated diagram describing thoughts.\n{mermaid_diagram}",
                                )
                    c.update_message_by_id(
                        message_id=thinking_id,
                        new_message=f"[ACTIVITY] Completed activities.",
                    )
                self.conversation.log_interaction(
                    role=self.agent_name,
                    message=response,
                )
                if self.conversation_name == "-":
                    # Rename the conversation
                    new_name = datetime.now().strftime(
                        "Conversation Created %Y-%m-%d %I:%M %p"
                    )
                    conversation_list = c.get_conversations()
                    new_convo = await self.inference(
                        user_input=f"Rename conversation",
                        prompt_name="Name Conversation",
                        conversation_list="\n".join(conversation_list),
                        conversation_results=10,
                        websearch=False,
                        browse_links=False,
                        voice_response=False,
                        log_user_input=False,
                        log_output=False,
                        conversation_name=self.conversation_name,
                    )

                    logging.info(f"New conversation name: {new_convo}")

                    # Extract JSON from the response
                    try:
                        # Check if the response contains a code block with JSON
                        if "```json" in new_convo:
                            json_text = (
                                new_convo.split("```json")[1].split("```")[0].strip()
                            )
                        elif "```" in new_convo:
                            # Check for plain code block that might contain JSON
                            json_text = (
                                new_convo.split("```")[1].split("```")[0].strip()
                            )
                        else:
                            # If no code block, try to extract anything that looks like JSON
                            json_start = new_convo.find("{")
                            json_end = new_convo.rfind("}")
                            if (
                                json_start != -1
                                and json_end != -1
                                and json_end > json_start
                            ):
                                json_text = new_convo[json_start : json_end + 1]
                            else:
                                raise ValueError("No valid JSON found in response")

                        # Parse the JSON
                        parsed_json = json.loads(json_text)
                        new_name = parsed_json.get(
                            "suggested_conversation_name", new_name
                        )
                        if new_name in conversation_list:
                            # Do not use the same name
                            new_convo = await self.inference(
                                user_input=f"**Do not use {new_name}!**",
                                prompt_name="Name Conversation",
                                conversation_list="\n".join(conversation_list),
                                conversation_results=10,
                                websearch=False,
                                browse_links=False,
                                voice_response=False,
                                log_user_input=False,
                                log_output=False,
                            )

                            logging.info(f"New conversation name #2: {new_convo}")

                            # Extract JSON again with same robust method
                            if "```json" in new_convo:
                                json_text = (
                                    new_convo.split("```json")[1]
                                    .split("```")[0]
                                    .strip()
                                )
                            elif "```" in new_convo:
                                json_text = (
                                    new_convo.split("```")[1].split("```")[0].strip()
                                )
                            else:
                                json_start = new_convo.find("{")
                                json_end = new_convo.rfind("}")
                                if (
                                    json_start != -1
                                    and json_end != -1
                                    and json_end > json_start
                                ):
                                    json_text = new_convo[json_start : json_end + 1]
                                else:
                                    raise ValueError(
                                        "No valid JSON found in second response"
                                    )

                            parsed_json = json.loads(json_text)
                            new_name = parsed_json.get(
                                "suggested_conversation_name", new_name
                            )

                            if new_name in conversation_list:
                                new_name = datetime.now().strftime(
                                    "Conversation Created %Y-%m-%d %I:%M %p"
                                )
                    except Exception as e:
                        import traceback

                        traceback.print_exc()
                        logging.error(f"Error renaming conversation: {e}")
                        if new_convo:
                            new_name = str(new_convo)
                    c.set_conversation_summary(summary=new_name)
                    self.conversation_name = c.rename_conversation(new_name=new_name)
        if isinstance(response, dict):
            response = json.dumps(response, indent=2)
        if not isinstance(response, str):
            response = str(response)
        try:
            prompt_tokens = get_tokens(new_prompt) + self.input_tokens
            completion_tokens = get_tokens(response)
            total_tokens = int(prompt_tokens) + int(completion_tokens)
            logging.info(f"Input tokens: {prompt_tokens}")
            logging.info(f"Completion tokens: {completion_tokens}")
            logging.info(f"Total tokens: {total_tokens}")
        except:
            if not response:
                response = "Unable to retrieve response."
                logging.error(f"Error getting response: {response}")
        response = self.remove_tagged_content(response, "execute")
        response = self.remove_tagged_content(response, "output")
        res_model = {
            "id": self.conversation_id,
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
        images: list = [],
        injected_memories: int = 100,
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
        injected_memories: int = 100,
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
            log_output=False,
        )
        rejected_async = self.inference(
            user_input=question,
            prompt_category="Default",
            prompt_name="Wrong Answers Only",
            log_user_input=False,
            log_output=False,
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
                injected_memories=100,
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

    def _generate_detailed_schema(self, model: Type[BaseModel], depth: int = 0) -> str:
        """
        Recursively generates a detailed schema representation of a Pydantic model,
        including nested models and complex types.
        """
        fields = get_type_hints(model)
        field_descriptions = []
        indent = "  " * depth
        for field, field_type in fields.items():
            description = f"{indent}{field}: "
            origin_type = get_origin(field_type)
            if origin_type is None:
                origin_type = field_type
            if inspect.isclass(origin_type) and issubclass(origin_type, BaseModel):
                description += f"Nested Model:\n{self._generate_detailed_schema(origin_type, depth + 1)}"
            elif origin_type == list:
                list_type = get_args(field_type)[0]
                if inspect.isclass(list_type) and issubclass(list_type, BaseModel):
                    description += f"List of Nested Model:\n{self._generate_detailed_schema(list_type, depth + 1)}"
                elif get_origin(list_type) == Union:
                    union_types = get_args(list_type)
                    description += f"List of Union:\n"
                    for union_type in union_types:
                        if inspect.isclass(union_type) and issubclass(
                            union_type, BaseModel
                        ):
                            description += f"{indent}  - Nested Model:\n{self._generate_detailed_schema(union_type, depth + 2)}"
                        else:
                            description += (
                                f"{indent}  - {self._get_type_name(union_type)}\n"
                            )
                else:
                    description += f"List[{self._get_type_name(list_type)}]"
            elif origin_type == dict:
                key_type, value_type = get_args(field_type)
                description += f"Dict[{self._get_type_name(key_type)}, {self._get_type_name(value_type)}]"
            elif origin_type == Union:
                union_types = get_args(field_type)

                for union_type in union_types:
                    if inspect.isclass(union_type) and issubclass(
                        union_type, BaseModel
                    ):
                        description += f"{indent}  - Nested Model:\n{self._generate_detailed_schema(union_type, depth + 2)}"
                    else:
                        type_name = self._get_type_name(union_type)
                        if type_name != "NoneType":
                            description += f"{self._get_type_name(union_type)}\n"
            elif inspect.isclass(origin_type) and issubclass(origin_type, Enum):
                enum_values = ", ".join([f"{e.name} = {e.value}" for e in origin_type])
                description += f"{origin_type.__name__} (Enum values: {enum_values})"
            else:
                description += self._get_type_name(origin_type)
            field_descriptions.append(description)
        return "\n".join(field_descriptions)

    def _get_type_name(self, type_):
        """Helper method to get the name of a type, handling some special cases."""
        if hasattr(type_, "__name__"):
            return type_.__name__
        return str(type_).replace("typing.", "")

    async def convert_to_model(
        self,
        input_string: str,
        model: Type[BaseModel],
        max_failures: int = 3,
        response_type: str = None,
        **kwargs,
    ):
        """
        Converts a string to a Pydantic model using an AGiXT agent.

        Args:
        input_string (str): The string to convert to a model.
        model (Type[BaseModel]): The Pydantic model to convert the string to.
        max_failures (int): The maximum number of times to retry the conversion if it fails.
        response_type (str): The type of response to return. Either 'json' or None. None will return the model.
        **kwargs: Additional arguments to pass to the AGiXT agent as prompt arguments.
        """
        input_string = str(input_string)
        schema = self._generate_detailed_schema(model)
        if "user_input" in kwargs:
            del kwargs["user_input"]
        if "schema" in kwargs:
            del kwargs["schema"]
        response = await self.inference(
            user_input=input_string,
            schema=schema,
            prompt_category="Default",
            prompt_name="Convert to Pydantic Model",
            log_user_input=False,
            log_output=False,
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
            return await self.convert_to_model(
                input_string=input_string,
                model=model,
                max_failures=max_failures,
                response_type=response_type,
                failures=failures,
            )

    def get_agent_workspace_markdown(self):
        def generate_markdown_structure(folder_path, indent=0):
            if not os.path.isdir(folder_path):
                return ""
            markdown_output = ""
            items = sorted(os.listdir(folder_path))
            for item in items:
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    markdown_output += f"{'  ' * indent}* **{item}/**\n"
                    markdown_output += generate_markdown_structure(
                        item_path, indent + 1
                    )
                else:
                    markdown_output += f"{'  ' * indent}* {item}\n"
            return markdown_output

        return generate_markdown_structure(folder_path=self.agent_workspace)

    async def analyze_user_input(self, user_input: str):
        code_execution = ""
        thinking_id = self.conversation.get_thinking_id(agent_name=self.agent_name)
        self.conversation.log_interaction(
            role=self.agent_name,
            message=f"[SUBACTIVITY][{thinking_id}] Analyzing.",
        )
        analyze_input = await self.inference(
            user_input=user_input,
            prompt_category="Default",
            prompt_name="Analyze Input",
            log_user_input=False,
            log_output=False,
            browse_links=False,
            websearch=False,
            websearch_depth=0,
            voice_response=False,
        )
        analyzed_input = {}
        logging.info(f"Analyzed Input: {analyze_input}")
        if "```json" not in analyze_input and "```" in analyze_input:
            analyze_input = analyze_input.replace("```", "```json", 1)
        if "```json" in analyze_input:
            analyze_input = analyze_input.split("```json")[1].split("```")[0]
        try:
            analyzed_input = json.loads(analyze_input)
            if "math" in analyzed_input:
                if str(analyzed_input["math"]).lower() != "true":
                    return ""
            else:
                return ""
        except:
            return ""
        if analyzed_input == {}:
            return ""
        code_interpreter = await self.inference(
            user_input=user_input,
            prompt_category="Default",
            prompt_name="Write Code",
            log_user_input=False,
            log_output=False,
            browse_links=False,
            websearch=False,
            websearch_depth=0,
            voice_response=False,
        )
        if "```" not in code_interpreter:
            code_interpreter = f"```python\n{code_interpreter}\n```"
        logging.info(f"Code Interpreter: {code_interpreter}")
        if "```python" in code_interpreter:
            code_interpreter = code_interpreter.split("```python")[1].split("```")[0]
            if "```python" in code_interpreter:
                code_interpreter = code_interpreter.split("```python")[1].split("```")[
                    0
                ]
            code_verification = await self.inference(
                user_input=user_input,
                prompt_category="Default",
                prompt_name="Verify Code",
                code=code_interpreter,
                log_user_input=False,
                log_output=False,
                browse_links=False,
                websearch=False,
                websearch_depth=0,
                voice_response=False,
            )
            if "```" not in code_verification:
                code_verification = f"```python\n{code_verification}\n```"
            logging.info(f"Code Verification: {code_verification}")
            if "```python" in code_verification:
                code_verification = code_verification.split("```python")[1].split(
                    "```"
                )[0]
                if "```python" in code_verification:
                    code_verification = code_verification.split("```python")[1].split(
                        "```"
                    )[0]
                try:
                    last_line = code_verification.split("\n")[-1]
                    if last_line == "\n" or last_line == "":
                        last_line = code_verification.split("\n")[-2]
                    if last_line == "\n" or last_line == "":
                        last_line = code_verification.split("\n")[-3]
                    if not last_line.startswith("print("):
                        old_last_line = last_line
                        new_last_line = f"print({last_line})"
                        code_verification = code_verification.rsplit(old_last_line, 1)[
                            0
                        ]
                        code_verification += new_last_line
                except Exception as e:
                    logging.error(f"Error adding print statement: {e}")
                try:
                    code_execution = await self.execute_command(
                        command_name="Execute Python Code",
                        command_args={"code": code_verification, "text": ""},
                    )
                except Exception as e:
                    fixed_code = await self.inference(
                        user_input=user_input,
                        prompt_category="Default",
                        prompt_name="Fix Verified Code",
                        code=code_verification,
                        code_error=str(e),
                        log_user_input=False,
                        log_output=False,
                        browse_links=False,
                        websearch=False,
                        websearch_depth=0,
                        voice_response=False,
                    )
                    if "```" not in fixed_code:
                        fixed_code = f"```python\n{fixed_code}\n```"
                    logging.info(f"Fixed Code: {fixed_code}")
                    code_verification = fixed_code
                    if "```python" in code_verification:
                        code_verification = code_verification.split("```python")[
                            1
                        ].split("```")[0]
                        if "```python" in code_verification:
                            code_verification = code_verification.split("```python")[
                                1
                            ].split("```")[0]
                        try:
                            code_execution = await self.execute_command(
                                command_name="Execute Python Code",
                                command_args={"code": code_verification, "text": ""},
                            )
                        except Exception as e:
                            code_execution = ""
                            logging.error(f"Error executing code: {e}")
        if code_execution != "":
            return f"Executed the following code expressed to assist the user:\n```python\n{code_verification}\n```\n**REFERENCE THE RESULTS, NOT THE CODE TO THE USER WHEN RESPONDING! THE RESULTS FROM RUNNING THE CODE ARE AS FOLLOWS:**\n{code_execution}"
        return ""

    async def fix_and_execute_code(
        self,
        user_input: str,
        code: str,
        code_error: str,
        file_content: str,
        file_preview: str = "",
        import_file: str = "",
        multifile: bool = False,
        failures: int = 0,
        max_failures: int = 5,
    ):
        code_failed = False
        fixed_code = await self.inference(
            user_input=user_input,
            prompt_category="Default",
            prompt_name="Fix Code",
            file_preview=file_preview,
            import_file=import_file,
            code=code,
            code_error=str(code_error),
            log_user_input=False,
            log_output=False,
            browse_links=False,
            websearch=False,
            websearch_depth=0,
            voice_response=False,
        )
        if "```python" in fixed_code:
            fixed_code = fixed_code.split("```python")[1].split("```")[0]
        if "```python" in fixed_code:
            fixed_code = fixed_code.split("```python")[1].split("```")[0]
        code_verification = await self.inference(
            user_input=user_input,
            prompt_category="Default",
            prompt_name=(
                "Verify Code Interpreter Multifile"
                if multifile
                else "Verify Code Interpreter"
            ),
            import_file=import_file,
            file_preview=file_preview,
            code=fixed_code,
            log_user_input=False,
            log_output=False,
            browse_links=False,
            websearch=False,
            websearch_depth=0,
            voice_response=False,
        )
        try:
            code_execution = await self.execute_command(
                command_name="Execute Python Code",
                command_args={"code": code_verification, "text": file_content},
            )
        except Exception:
            code_failed = True
        if code_execution.startswith("Error"):
            code_failed = True
        if code_failed:
            failures += 1
            if failures >= max_failures:
                return code_verification
            return await self.fix_and_execute_code(
                user_input=user_input,
                code=code_verification,
                code_error=str(code_execution),
                file_content=file_content,
                file_preview=file_preview,
                import_file=import_file,
                failures=failures,
                max_failures=max_failures,
            )

    async def analyze_data(
        self,
        user_input: str,
        file_content=None,
        file_name="",
        max_failures: int = 5,
    ):
        file_names = []
        file_path = self.conversation_workspace
        thinking_id = self.conversation.get_thinking_id(agent_name=self.agent_name)
        if "```csv" in user_input and file_name == "":
            file_name = f"{uuid.uuid4().hex}.csv"
            self.conversation.log_interaction(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{thinking_id}] Saving CSV data to file `{file_name}`.",
            )
            file_content = user_input.split("```csv")[1].split("```")[0]
            file_path = os.path.join(self.conversation_workspace, file_name)
            with open(file_path, "w") as f:
                f.write(file_content)
        if not file_content:
            files = os.listdir(self.conversation_workspace)
            logging.info(f"Files in conversation workspace: {files}")
            # Check if any files are csv files, if not, return empty string
            csv_files = [file for file in files if file.endswith(".csv")]
            logging.info(f"CSV files in conversation workspace: {csv_files}")
            if len(csv_files) == 0:
                return await self.analyze_user_input(user_input=user_input)
            activities = self.conversation.get_activities(limit=20)["activities"]
            logging.info(f"Activities: {activities}")
            if len(activities) == 0:
                return await self.analyze_user_input(user_input=user_input)
            likely_files = []
            for activity in activities:
                if ".csv" in activity["message"]:
                    if "`" in activity["message"]:
                        likely_files.append(activity["message"].split("`")[1])
            if len(likely_files) == 1:
                file_name = likely_files[0]
                file_path = os.path.join(self.conversation_workspace, file_name)
                file_content = open(file_path, "r").read()
            else:
                file_determination = await self.inference(
                    user_input=user_input,
                    prompt_category="Default",
                    prompt_name="Determine File",
                    directory_listing="\n".join(csv_files),
                    conversation_results=10,
                    websearch=False,
                    browse_links=False,
                    log_user_input=False,
                    log_output=False,
                    voice_response=False,
                )
                # Iterate over files and use regex to see if the file name is in the response
                for file in files:
                    if re.search(file, file_determination):
                        file_names.append(file)
                if len(file_names) == 1:
                    file_name = file_names[0]
                    file_path = os.path.join(self.conversation_workspace, file_name)
                    file_content = open(file_path, "r").read()
            if file_name == "":
                return await self.analyze_user_input(user_input=user_input)
        if len(file_names) > 1:
            # Found multiple files, do things a little differently.
            previews = []
            import_files = ""
            for file in file_names:
                if import_files == "":
                    import_files = f"`{self.conversation_workspace}/{file}`"
                else:
                    import_files += f", `{self.conversation_workspace}/{file}`"
                file_path = os.path.join(self.conversation_workspace, file)
                file_content = open(file_path, "r").read()
                lines = file_content.split("\n")
                lines = lines[:2]
                file_preview = "\n".join(lines)
                previews.append(f"`{file_path}`\n```csv\n{file_preview}\n```")
            file_preview = "\n".join(previews)
            self.conversation.log_interaction(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{thinking_id}] Analyzing data from multiple files: {import_files}.",
            )
        else:
            lines = file_content.split("\n")
            if len(lines) > 5:
                lines = lines[:5]
            else:
                lines = lines[:2]
            file_preview = "\n".join(lines)
            self.conversation.log_interaction(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{thinking_id}] Analyzing data from file `{file_name}`.",
            )
        code_interpreter = await self.inference(
            user_input=user_input,
            prompt_category="Default",
            prompt_name=(
                "Code Interpreter Multifile"
                if len(file_names) > 1
                else "Code Interpreter"
            ),
            import_file=import_files if len(file_names) > 1 else file_path,
            file_preview=file_preview,
            log_user_input=False,
            log_output=False,
            browse_links=False,
            websearch=False,
            websearch_depth=0,
            voice_response=False,
        )
        if "```python" in code_interpreter:
            code_interpreter = code_interpreter.split("```python")[1].split("```")[0]
        if "```python" in code_interpreter:
            code_interpreter = code_interpreter.split("```python")[1].split("```")[0]
        # Step 5 - Verify the code is good before executing it.
        import_file = import_files if len(file_names) > 1 else file_path
        code_verification = await self.inference(
            user_input=user_input,
            prompt_category="Default",
            prompt_name=(
                "Verify Code Interpreter Multifile"
                if len(file_names) > 1
                else "Verify Code Interpreter"
            ),
            import_file=import_file,
            file_preview=file_preview,
            code=code_interpreter,
            log_user_input=False,
            log_output=False,
            browse_links=False,
            websearch=False,
            websearch_depth=0,
            voice_response=False,
        )
        # Split out the python code
        if "```python" in code_verification:
            code_verification = code_verification.split("```python")[1].split("```")[0]
        if "```python" in code_verification:
            code_verification = code_verification.split("```python")[1].split("```")[0]
        # Step 6 - Execute the code
        code_failed = False
        try:
            code_execution = await self.execute_command(
                command_name="Execute Python Code",
                command_args={"code": code_verification, "text": file_content},
            )
        except Exception as e:
            code_failed = True
        if code_execution.startswith("Error"):
            code_failed = True
        # Step 7 - If the code failed to run without error, attempt fix the code and try again {max_failures} times
        if code_failed:
            code_execution = await self.fix_and_execute_code(
                user_input=user_input,
                code=code_verification,
                code_error=str(code_execution),
                file_content=file_content,
                file_preview=file_preview,
                import_file=import_file,
                max_failures=max_failures,
            )
        if code_execution.startswith("Error"):
            self.conversation.log_interaction(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{thinking_id}][ERROR] Unable to complete data analysis.",
            )
            return f"Data analysis failed after {max_failures} attempts. Advise the user that there may be an issue with the data and to try again in a new conversation."
        return f"**REFERENCE ALL OF THE FOLLOWING OUTPUT FROM DATA ANALYSIS RESULTS ON {import_files if len(file_names) > 1 else file_path} INCLUDING ALL VISUALIZATIONS IN MARKDOWN FORMAT TO THE USER. REFERENCE EXACT LINKS TO IMAGES OR FILES IF PRESENT HERE! Do not rename files!**\n\n{code_execution}"
