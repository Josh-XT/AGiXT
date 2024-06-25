from Interactions import Interactions
from ApiClient import get_api_client, Conversations, Prompts, Chain
from readers.file import FileReader
from Extensions import Extensions
from pydub import AudioSegment
from Globals import getenv, get_tokens, DEFAULT_SETTINGS
from Models import ChatCompletions, TasksToDo, ChainCommandName
from Websearch import Websearch
from datetime import datetime
from typing import Type, get_args, get_origin, Union, List
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
import os
import re
import base64
import uuid
import json
import time


class AGiXT:
    def __init__(self, user: str, agent_name: str, api_key: str):
        self.user_email = user.lower()
        if api_key is not None:
            self.api_key = str(api_key).replace("Bearer ", "").replace("bearer ", "")
        else:
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
        self.agent_workspace = self.agent.working_directory
        os.makedirs(self.agent_workspace, exist_ok=True)
        self.outputs = f"{self.uri}/outputs/{self.agent.agent_id}"
        self.failures = 0

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
        conversation_name: str = "",
        images: list = [],
        injected_memories: int = 10,
        conversation_results: int = 10,
        shots: int = 1,
        browse_links: bool = False,
        voice_response: bool = False,
        log_user_input: bool = True,
        log_output: bool = True,
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
            conversation_name (str): Name of the conversation
            browse_links (bool): Whether to browse links in the response
            images (list): List of image file paths
            shots (int): Number of responses to generate
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
                injected_memories = 10
            del kwargs["context_results"]
        if "tts" in kwargs:
            voice_response = str(kwargs["tts"]).lower() == "true"
            del kwargs["tts"]
        return await self.agent_interactions.run(
            user_input=user_input,
            prompt_category=prompt_category,
            prompt_name=prompt_name,
            context_results=injected_memories,
            conversation_results=conversation_results,
            shots=shots,
            conversation_name=conversation_name,
            browse_links=browse_links,
            images=images,
            tts=voice_response,
            log_user_input=log_user_input,
            log_output=log_output,
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

    async def text_to_speech(
        self,
        text: str,
        conversation_name: str = "",
        log_output: bool = False,
    ):
        """
        Generate Text to Speech audio from text

        Args:
            text (str): Text to convert to speech
            conversation_name (str): Name of the conversation
            log_output (bool): Whether to log the output

        Returns:
            str: URL of the generated audio
        """
        if conversation_name != "" and conversation_name != None:
            c = Conversations(conversation_name=conversation_name, user=self.user_email)
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Generating audio response.",
            )
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
            c.log_interaction(
                role=self.agent_name,
                message=f'<audio controls><source src="{tts_url}" type="audio/wav"></audio>',
            )
        return tts_url

    async def audio_to_text(self, audio_path: str, conversation_name: str = ""):
        """
        Audio to Text transcription

        Args:
            audio_path (str): Path to the audio file
            conversation_name (str): Name of the conversation

        Returns
            str: Transcription of the audio
        """
        if conversation_name != "" and conversation_name != None:
            c = Conversations(conversation_name=conversation_name, user=self.user_email)
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Transcribing recorded audio.",
            )
            # Start a timer
            start = time.time()
        response = await self.agent.transcribe_audio(audio_path=audio_path)
        if conversation_name != "" and conversation_name != None:
            # End the timer
            end = time.time()
            elapsed_time = end - start
            elapsed_time = "{:.2f}".format(elapsed_time)
            c.log_interaction(
                role=self.agent_name,
                message=f"Transcribed audio in {elapsed_time} seconds.",
            )
        return response

    async def translate_audio(self, audio_path: str, conversation_name: str = ""):
        """
        Translate an audio file

        Args:
            audio_path (str): Path to the audio file
            conversation_name (str): Name of the conversation

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
        log_output: bool = False,
    ):
        """
        Execute a command with arguments

        Args:
            command_name (str): Name of the command to execute
            command_args (dict): Arguments for the command
            conversation_name (str): Name of the conversation
            voice_response (bool): Whether to generate a voice response
            log_output (bool): Whether to log the output

        Returns:
            str: Response from the command
        """
        if conversation_name != "" and conversation_name != None:
            c = Conversations(conversation_name=conversation_name, user=self.user_email)
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Executing command `{command_name}` with args:\n```json\n{json.dumps(command_args, indent=2)}```",
            )
        response = await Extensions(
            agent_name=self.agent_name,
            agent_config=self.agent.AGENT_CONFIG,
            conversation_name=f"{command_name} Execution History",
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
                await self.text_to_speech(
                    text=response,
                    conversation_name=conversation_name,
                    log_output=log_output,
                )
        if log_output:
            c.log_interaction(role=self.agent_name, message=response)
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
                    if conversation_name != "" and conversation_name != None:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[ACTIVITY] Executing command `{step['prompt']['command_name']}` with args:\n```json\n{json.dumps(args, indent=2)}```",
                        )
                    result = await self.execute_command(
                        command_name=step["prompt"]["command_name"],
                        command_args=args,
                        conversation_name=conversation_name,
                        voice_response=False,
                    )
                elif prompt_type == "prompt":
                    if conversation_name != "" and conversation_name != None:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[ACTIVITY] Running prompt: {prompt_name} with args:\n```json\n{json.dumps(args, indent=2)}```",
                        )
                    if "prompt_name" not in args:
                        args["prompt_name"] = prompt_name
                    if "user_input" in args:
                        user_input = args["user_input"]
                        del args["user_input"]
                    if prompt_name != "":
                        result = await self.inference(
                            agent_name=agent_name,
                            user_input=user_input,
                            log_user_input=False,
                            **args,
                        )
                elif prompt_type == "chain":
                    if conversation_name != "" and conversation_name != None:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[ACTIVITY] Running chain: {args['chain']} with args:\n```json\n{json.dumps(args, indent=2)}```",
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
        if conversation_name != "":
            c.log_interaction(
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
                        conversation_name=conversation_name,
                    )
                    step_responses.append(task)
        logging.info(f"Step responses: {step_responses}")
        if step_responses:
            response = step_responses[-1]
        if response == None:
            return f"Chain failed to complete, it failed on step {step_data['step']}. You can resume by starting the chain from the step that failed with chain ID {chain_run_id}."
        c.log_interaction(role=self.agent_name, message=response)
        if "tts_provider" in self.agent_settings and voice_response:
            if (
                self.agent_settings["tts_provider"] != "None"
                and self.agent_settings["tts_provider"] != ""
                and self.agent_settings["tts_provider"] != None
            ):
                await self.text_to_speech(
                    text=response, conversation_name=conversation_name, log_output=True
                )
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
        collection_id: str = "1",
        conversation_name: str = "",
    ):
        """
        Learn from a file

        Args:
            file_url (str): URL of the file
            file_name (str): Name of the file
            user_input (str): User input to the agent
            collection_id (str): Collection ID to save the file to
            conversation_name (str): Name of the conversation

        Returns:
            str: Response from the agent
        """
        logging.info(f"Learning from file: {file_url}")
        logging.info(f"File name: {file_name}")
        logging.info(f"User input: {user_input}")
        logging.info(f"Collection ID: {collection_id}")
        logging.info(f"Conversation name: {conversation_name}")
        logging.info(f"Agent workspace: {self.agent_workspace}")
        logging.info(f"Outputs: {self.outputs}")
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
            file_name = file_data["file_name"]
            file_path = os.path.normpath(os.path.join(self.agent_workspace, file_name))
        logging.info(f"File path: {file_path}")
        if not file_path.startswith(self.agent_workspace):
            file_path = os.path.normpath(os.path.join(self.agent_workspace, file_name))
            logging.info(f"Corrected file path: {file_path}")
        file_type = file_name.split(".")[-1]
        c = Conversations(conversation_name=conversation_name, user=self.user_email)
        if (
            conversation_name != ""
            and conversation_name != None
            and file_type not in ["jpg", "jpeg", "png", "gif"]
        ):
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Reading [{file_name}]({file_url}) into memory.",
            )
        if file_type in ["ppt", "pptx"]:
            # Convert it to a PDF
            pdf_file_path = file_path.replace(".pptx", ".pdf").replace(".ppt", ".pdf")
            file_name = str(file_name).replace(".pptx", ".pdf").replace(".ppt", ".pdf")
            if conversation_name != "" and conversation_name != None:
                c.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY] Converting PowerPoint file [{file_name}]({file_url}) to PDF.",
                )
            try:
                subprocess.run(
                    [
                        "libreoffice",
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        self.agent_workspace,
                        file_path,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except Exception as e:
                logging.error(f"Error converting PowerPoint to PDF: {e}")
            file_path = pdf_file_path
        if user_input == "":
            user_input = "Describe each stage of this image."
        file_reader = FileReader(
            agent_name=self.agent_name,
            agent_config=self.agent.AGENT_CONFIG,
            collection_number=collection_id,
            ApiClient=self.ApiClient,
            user=self.user_email,
        )
        disallowed_types = ["exe", "bin", "rar", "ppt", "pptx"]
        if file_type in disallowed_types:
            response = f"[ERROR] I was unable to read the file called `{file_name}`."
        elif file_type == "pdf":
            with pdfplumber.open(file_path) as pdf:
                content = "\n".join([page.extract_text() for page in pdf.pages])
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await file_reader.write_text_to_memory(
                user_input=user_input,
                text=f"Content from PDF uploaded at {timestamp} named `{file_name}`:\n{content}",
                external_source=f"file {file_path}",
            )
            response = f"Read [{file_name}]({file_url}) into memory."
        elif file_path.endswith(".zip"):
            extracted_zip_folder_name = f"extracted_{file_name.replace('.zip', '_zip')}"
            new_folder = os.path.normpath(
                os.path.join(self.agent_workspace, extracted_zip_folder_name)
            )
            if new_folder.startswith(self.agent_workspace):
                with zipfile.ZipFile(file_path, "r") as zipObj:
                    zipObj.extractall(path=new_folder)
                # Iterate over every file that was extracted including subdirectories
                for root, dirs, files in os.walk(new_folder):
                    for name in files:
                        current_folder = root.replace(new_folder, "")
                        output_url = f"{self.outputs}/{extracted_zip_folder_name}/{current_folder}/{name}"
                        logging.info(f"Output URL: {output_url}")
                        await self.learn_from_file(
                            file_url=output_url,
                            file_name=name,
                            user_input=user_input,
                            collection_id=collection_id,
                            conversation_name=conversation_name,
                        )
                response = f"Extracted the content of the zip file [{file_name}]({file_url}) and read them into memory."
            else:
                response = (
                    f"[ERROR] I was unable to read the file called `{file_name}`."
                )
        elif file_type == "xlsx" or file_type == "xls":
            df = pd.read_excel(file_path)
            # Check if the spreadsheet has multiple sheets
            if isinstance(df, dict):
                sheet_names = list(df.keys())
                x = 0
                csv_files = []
                for sheet_name in sheet_names:
                    x += 1
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                    file_path = file_path.replace(f".{file_type}", f"_{x}.csv")
                    csv_file_name = os.path.basename(file_path)
                    df.to_csv(file_path, index=False)
                    csv_files.append(
                        f"[{csv_file_name}]({self.outputs}/{csv_file_name})"
                    )
                    await self.learn_from_file(
                        file_url=f"{self.outputs}/{csv_file_name}",
                        file_name=csv_file_name,
                        user_input=f"Original file: {file_name}\nSheet: {sheet_name}\nNew file: {csv_file_name}\n{user_input}",
                        collection_id=collection_id,
                        conversation_name=conversation_name,
                    )
                str_csv_files = ", ".join(csv_files)
                response = f"Separated the content of the spreadsheet called `{file_name}` into {x} files called {str_csv_files} and read them into memory."
            else:
                # Save it as a CSV file and run this function again
                file_path = file_path.replace(f".{file_type}", ".csv")
                csv_file_name = os.path.basename(file_path)
                df.to_csv(file_path, index=False)
                return await self.learn_from_file(
                    file_url=f"{self.outputs}/{csv_file_name}",
                    file_name=csv_file_name,
                    user_input=f"Original file: {file_name}\nNew file: {csv_file_name}\n{user_input}",
                    collection_id=collection_id,
                    conversation_name=conversation_name,
                )
        elif file_path.endswith(".doc") or file_path.endswith(".docx"):
            file_content = docx2txt.process(file_path)
            await file_reader.write_text_to_memory(
                user_input=user_input,
                text=file_content,
                external_source=f"file {file_path}",
            )
            response = f"Read [{file_name}]({file_url}) into memory."
        elif file_type == "csv":
            df = pd.read_csv(file_path)
            df_dict = df.to_dict()
            for line in df_dict:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                message = f"Content from file uploaded at {timestamp} named `{file_name}`:\n```json\n{json.dumps(df_dict[line], indent=2)}```\n"
                await file_reader.write_text_to_memory(
                    user_input=f"{user_input}\n{message}",
                    text=message,
                    external_source=f"file {file_path}",
                )
            response = f"Read [{file_name}]({file_url}) into memory."
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
            if conversation_name != "" and conversation_name != None:
                c.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY] Transcribing audio file [{file_name}]({file_url}) into memory.",
                )
            audio_response = await self.audio_to_text(audio_path=file_path)
            await file_reader.write_text_to_memory(
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
                if conversation_name != "" and conversation_name != None:
                    c.log_interaction(
                        role=self.agent_name,
                        message=f"[ACTIVITY] Uploaded `{file_name}` ![Uploaded {file_name}]({file_url})",
                    )
                try:
                    vision_prompt = f"The assistant has an image in context\nThe user's last message was: {user_input}\nThe uploaded image is `{file_name}`.\n\nAnswer anything relevant to the image that the user is questioning if anything, additionally, describe the image in detail."
                    vision_response = await self.agent.vision_inference(
                        prompt=vision_prompt, images=[file_url]
                    )
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    await file_reader.write_text_to_memory(
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
                with open(fp, "r") as f:
                    file_content = f.read()
                # Check how many lines are in the file content
                lines = file_content.split("\n")
                if len(lines) > 1:
                    for line_number, line in enumerate(lines):
                        await file_reader.write_text_to_memory(
                            user_input=user_input,
                            text=f"Content from file uploaded named `{file_name}` at {timestamp} on line number {line_number + 1}:\n{line}",
                            external_source=f"file {fp}",
                        )
                else:
                    await file_reader.write_text_to_memory(
                        user_input=user_input,
                        text=f"Content from file uploaded named `{file_name}` at {timestamp}:\n{file_content}",
                        external_source=f"file {fp}",
                    )
                response = f"Read [{file_name}]({file_url}) into memory."
            else:
                response = (
                    f"[ERROR] I was unable to read the file called `{file_name}`."
                )
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
            if "," in url:
                file_type = url.split(",")[0].split("/")[1].split(";")[0]
                file_data = base64.b64decode(url.split(",")[1])
            else:
                file_type = file_name.split(".")[-1]
                file_data = base64.b64decode(url)
            full_path = os.path.normpath(os.path.join(self.agent_workspace, file_name))
            if not full_path.startswith(self.agent_workspace):
                raise Exception("Path given not allowed")
            with open(file_path, "wb") as f:
                f.write(file_data)
            url = f"{self.outputs}/{file_name}"
            return {"file_name": file_name, "file_url": url}

    async def plan_task(
        self,
        user_input: str,
        websearch: bool = False,
        websearch_depth: int = 3,
        conversation_name: str = "",
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
        conversation_name (str): Name of the conversation to log activity to
        log_user_input (bool): Whether to log the user input
        log_output (bool): Whether to log the output
        enable_new_command (bool): Whether to enable the new command for the agent

        Returns:
        str: The name of the created chain
        """
        c = Conversations(conversation_name=conversation_name, user=self.user_email)
        if log_user_input:
            c.log_interaction(
                role="USER",
                message=user_input,
            )
        c.log_interaction(
            role=self.agent_name,
            message=f"[ACTIVITY] Determining primary objective.",
        )
        # primary_objective = Step 1, execute chain "Smart Prompt" with the user input to get Primary Objective
        primary_objective = await self.execute_chain(
            chain_name="Smart Prompt",
            user_input=user_input,
            agent_override=self.agent_name,
            log_user_input=False,
            conversation_name=conversation_name,
        )
        chain_name = await self.inference(
            user_input=user_input,
            introduction=primary_objective,
            prompt_category="Default",
            prompt_name="Title a Chain",
            log_output=False,
            log_user_input=False,
            conversation_name=conversation_name,
        )
        chain_title = await self.convert_to_pydantic_model(
            input_string=chain_name,
            model=ChainCommandName,
        )
        chain_name = chain_title.command_name
        c.log_interaction(
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
            injected_memories=10,
            log_output=False,
            log_user_input=False,
            conversation_name=conversation_name,
        )
        task_list = await self.convert_to_pydantic_model(
            input_string=numbered_list_of_tasks,
            model=TasksToDo,
        )
        self.chain.add_chain(chain_name=chain_name)
        c.log_interaction(
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
            c.log_interaction(
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
            c.log_interaction(
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
        conversation_name: str = "",
        log_user_input: bool = True,
        log_output: bool = True,
        enable_new_command: bool = True,
    ):
        """
        Modify the chain based on user input

        Args:
        chain_name (str): Name of the chain to update
        user_input (str): User input to the agent
        conversation_name (str): Name of the conversation
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
            conversation_name=conversation_name,
            log_user_input=log_user_input,
            log_output=log_output,
            enable_new_command=enable_new_command,
        )

    async def chat_completions(self, prompt: ChatCompletions):
        """
        Generate an OpenAI style chat completion response with a ChatCompletion prompt

        Args:
            prompt (ChatCompletions): Chat completions prompt

        Returns:
            dict: Chat completion response
        """
        conversation_name = prompt.user
        c = Conversations(conversation_name=conversation_name, user=self.user_email)
        conversation_id = c.get_conversation_id()
        urls = []
        files = []
        new_prompt = ""
        browse_links = True
        tts = False
        websearch = False
        if "websearch" in self.agent_settings:
            websearch = str(self.agent_settings["websearch"]).lower() == "true"
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
        if "conversation_results" in self.agent_settings:
            conversation_results = int(self.agent_settings["conversation_results"])
        else:
            conversation_results = 6
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
                                                    self.agent_workspace, file_name
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
                                                        "file_url": f"{self.outputs}/{file_name}",
                                                    }
                                                )
                                        else:
                                            urls.append(url)
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
                                    if os.path.normpath(audio_file_path).startswith(
                                        self.agent_workspace
                                    ):
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
        for file in files:
            new_prompt += f"\nUploaded file: `{file['file_name']}`."
        c.log_interaction(role="USER", message=new_prompt)
        conversation_id = c.get_conversation_id()
        for file in files:
            await self.learn_from_file(
                file_url=file["file_url"],
                file_name=file["file_name"],
                user_input=new_prompt,
                collection_id=conversation_id,
                conversation_name=conversation_name,
            )
        await self.learn_from_websites(
            urls=urls,
            scrape_depth=3,
            summarize_content=False,
            conversation_name=conversation_name,
        )
        await self.analyze_csv(
            user_input=new_prompt,
            conversation_name=conversation_name,
            file_content=None,
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
                conversation_results=conversation_results,
                shots=prompt.n,
                websearch=websearch,
                browse_links=browse_links,
                voice_response=tts,
                log_user_input=False,
                **prompt_args,
            )
        try:
            prompt_tokens = get_tokens(new_prompt)
            completion_tokens = get_tokens(response)
            total_tokens = int(prompt_tokens) + int(completion_tokens)
        except:
            if not response:
                response = "Unable to retrieve response."
                logging.error(f"Error getting response: {response}")
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

    async def convert_to_pydantic_model(
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
            return await self.convert_to_pydantic_model(
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

    async def analyze_csv(
        self,
        user_input: str,
        conversation_name: str,
        file_content=None,
    ):
        c = Conversations(conversation_name=conversation_name, user=self.user_email)
        file_names = []
        file_name = ""
        if not file_content:
            files = os.listdir(self.agent_workspace)
            # Check if any files are csv files, if not, return empty string
            csv_files = [file for file in files if file.endswith(".csv")]
            if len(csv_files) == 0:
                return ""
            activities = c.get_activities(limit=20)["activities"]
            if len(activities) == 0:
                return ""
            likely_files = []
            for activity in activities:
                if ".csv" in activity["message"]:
                    if "`" in activity["message"]:
                        likely_files.append(activity["message"].split("`")[1])
            if len(likely_files) == 0:
                return ""
            elif len(likely_files) == 1:
                file_name = likely_files[0]
                file_path = os.path.join(self.agent_workspace, file_name)
                file_content = open(file_path, "r").read()
            else:
                file_determination = await self.inference(
                    user_input=user_input,
                    prompt_category="Default",
                    prompt_name="Determine File",
                    directory_listing="\n".join(csv_files),
                    conversation_results=10,
                    conversation_name=conversation_name,
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
                    file_path = os.path.join(self.agent_workspace, file_name)
                    file_content = open(file_path, "r").read()
            if file_name == "":
                return ""
        if len(file_names) > 1:
            # Found multiple files, do things a little differently.
            previews = []
            import_files = ""
            for file in file_names:
                if import_files == "":
                    import_files = f"`{self.agent_workspace}/{file}`"
                else:
                    import_files += f", `{self.agent_workspace}/{file}`"
                file_path = os.path.join(self.agent_workspace, file)
                file_content = open(file_path, "r").read()
                lines = file_content.split("\n")
                lines = lines[:2]
                file_preview = "\n".join(lines)
                previews.append(f"`{file_path}`\n```csv\n{file_preview}\n```")
            file_preview = "\n".join(previews)
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Analyzing data from multiple files: {import_files}.",
            )
        else:
            lines = file_content.split("\n")
            lines = lines[:2]
            file_preview = "\n".join(lines)
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Analyzing data from file.",
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
            conversation_name=conversation_name,
            log_user_input=False,
            log_output=False,
            browse_links=False,
            websearch=False,
            websearch_depth=0,
            voice_response=False,
        )
        # Step 5 - Verify the code is good before executing it.
        code_verification = await self.inference(
            user_input=user_input,
            prompt_category="Default",
            prompt_name=(
                "Verify Code Interpreter Multifile"
                if len(file_names) > 1
                else "Verify Code Interpreter"
            ),
            import_file=import_files if len(file_names) > 1 else file_path,
            file_preview=file_preview,
            code=code_interpreter,
            conversation_name=conversation_name,
            log_user_input=False,
            log_output=False,
            browse_links=False,
            websearch=False,
            websearch_depth=0,
            voice_response=False,
        )
        # Step 6 - Execute the code, will need to revert to step 4 if the code is not correct to try again.
        code_execution = await self.execute_command(
            command_name="Execute Python Code",
            command_args={"code": code_verification, "text": file_content},
            conversation_name=conversation_name,
        )
        if not code_execution.startswith("Error"):
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] Data analysis complete.",
            )
            c.log_interaction(
                role=self.agent_name,
                message=f"## Results from analyzing data:\n{code_execution}",
            )
        else:
            self.failures += 1
            if self.failures < 3:
                c.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY][WARN] Data analysis failed, trying again ({self.failures}/3).",
                )
                return await self.analyze_csv(
                    user_input=user_input,
                    conversation_name=conversation_name,
                    file_content=file_content,
                )
            else:
                c.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY][ERROR] Data analysis failed after 3 attempts.",
                )
        return code_execution
