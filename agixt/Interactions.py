import re
import os
import regex
import json
import time
import spacy
from datetime import datetime
from Agent import Agent
from Prompts import Prompts
from extensions.searxng import searxng
from Chain import Chain, get_chain_responses_file_path, create_command_suggestion_chain
from urllib.parse import urlparse
import logging
from concurrent.futures import Future
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup


class Interactions:
    def __init__(self, agent_name: str = ""):
        if agent_name != "":
            self.agent_name = agent_name
            self.agent = Agent(self.agent_name)
            self.agent_commands = self.agent.get_commands_string()
            self.memories = self.agent.get_memories()
        else:
            self.agent_name = ""
            self.agent = None
            self.agent_commands = ""
            self.memories = None
        self.stop_running_event = None
        self.browsed_links = []
        self.failures = 0
        self.nlp = None

    def load_spacy_model(self):
        if not self.nlp:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except:
                spacy.cli.download("en_core_web_sm")
                self.nlp = spacy.load("en_core_web_sm")
        self.nlp.max_length = 99999999999999999999999

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

    def get_step_response(self, chain_name, step_number):
        base_path = os.path.join(os.getcwd(), "chains")
        file_path = os.path.normpath(
            os.path.join(base_path, chain_name, "responses.json")
        )
        if not file_path.startswith(base_path):
            raise ValueError("Invalid path, chain name must not contain slashes.")
        try:
            with open(file_path, "r") as f:
                responses = json.load(f)
            return responses.get(str(step_number))
        except:
            return ""

    def get_step_content(self, chain_name, prompt_content, user_input, agent_name):
        new_prompt_content = {}
        if isinstance(prompt_content, dict):
            for arg, value in prompt_content.items():
                if isinstance(value, str):
                    if "{user_input}" in value:
                        value = value.replace("{user_input}", user_input)
                    if "{agent_name}" in value:
                        value = value.replace("{agent_name}", agent_name)
                    if "{STEP" in value:
                        # Count how many times {STEP is in the value
                        step_count = value.count("{STEP")
                        for i in range(step_count):
                            # Get the step number from value between {STEP and }
                            new_step_number = int(value.split("{STEP")[1].split("}")[0])
                            # get the response from the step number
                            step_response = self.get_step_response(
                                chain_name=chain_name, step_number=new_step_number
                            )
                            # replace the {STEPx} with the response
                            if step_response:
                                resp = (
                                    step_response["response"]
                                    if "response" in step_response
                                    else f"{step_response}"
                                )
                                value = value.replace(
                                    f"{{STEP{new_step_number}}}",
                                    f"{resp}",
                                )
                new_prompt_content[arg] = value
        elif isinstance(prompt_content, str):
            new_prompt_content = prompt_content
            if "{user_input}" in prompt_content:
                new_prompt_content = new_prompt_content.replace(
                    "{user_input}", user_input
                )
            if "{agent_name}" in new_prompt_content:
                new_prompt_content = new_prompt_content.replace(
                    "{agent_name}", agent_name
                )
            if "{STEP" in prompt_content:
                step_count = value.count("{STEP")
                for i in range(step_count):
                    # Get the step number from value between {STEP and }
                    new_step_number = int(
                        prompt_content.split("{STEP")[1].split("}")[0]
                    )
                    # get the response from the step number
                    step_response = self.get_step_response(
                        chain_name=chain_name, step_number=new_step_number
                    )
                    # replace the {STEPx} with the response
                    if step_response:
                        resp = (
                            step_response["response"]
                            if "response" in step_response
                            else f"{step_response}"
                        )
                        new_prompt_content = prompt_content.replace(
                            f"{{STEP{new_step_number}}}", f"{resp}"
                        )
            if new_prompt_content == {}:
                new_prompt_content = prompt_content
        return new_prompt_content

    async def format_prompt(
        self,
        user_input: str = "",
        top_results: int = 5,
        prompt="",
        chain_name="",
        step_number=0,
        memories=None,
        **kwargs,
    ):
        cp = Prompts()
        if prompt == "":
            prompt = user_input
        else:
            try:
                prompt = cp.get_prompt(prompt_name=prompt, model=self.agent.AI_MODEL)
            except:
                prompt = prompt
        if top_results == 0:
            context = "None"
        else:
            try:
                context = await memories.context_agent(
                    query=user_input, top_results_num=top_results
                )
            except:
                context = "None."
        command_list = self.agent.get_commands_string()
        if chain_name != "":
            try:
                for arg, value in kwargs.items():
                    if "{STEP" in value:
                        # get the response from the step number
                        step_response = self.get_step_response(
                            chain_name=chain_name, step_number=step_number
                        )
                        # replace the {STEPx} with the response
                        value = value.replace(f"{{STEP{step_number}}}", step_response)
                        kwargs[arg] = value
            except:
                logging.info("No args to replace.")
            if "{STEP" in prompt:
                step_response = self.get_step_response(
                    chain_name=chain_name, step_number=step_number
                )
                prompt = prompt.replace(f"{{STEP{step_number}}}", step_response)
            if "{STEP" in user_input:
                step_response = self.get_step_response(
                    chain_name=chain_name, step_number=step_number
                )
                user_input = user_input.replace(f"{{STEP{step_number}}}", step_response)
        formatted_prompt = self.custom_format(
            string=prompt,
            user_input=user_input,
            agent_name=self.agent_name,
            COMMANDS=self.agent_commands,
            context=context,
            command_list=command_list,
            date=datetime.now().strftime("%B %d, %Y %I:%M %p"),
            **kwargs,
        )

        if not self.nlp:
            self.load_spacy_model()
        tokens = len(self.nlp(formatted_prompt))
        logging.info(f"FORMATTED PROMPT: {formatted_prompt}")
        return formatted_prompt, prompt, tokens

    async def run(
        self,
        user_input: str = "",
        prompt: str = "",
        context_results: int = 5,
        websearch: bool = False,
        websearch_depth: int = 3,
        learn_file: str = "",
        chain_name: str = "",
        step_number: int = 0,
        shots: int = 1,
        disable_memory: bool = False,
        **kwargs,
    ):
        shots = int(shots)
        if learn_file != "":
            try:
                learning_file = await self.memories.mem_read_file(file_path=learn_file)
            except:
                return "Failed to read file."
            if learning_file == False:
                return "Failed to read file."
        formatted_prompt, unformatted_prompt, tokens = await self.format_prompt(
            user_input=user_input,
            top_results=context_results,
            prompt=prompt,
            chain_name=chain_name,
            step_number=step_number,
            memories=self.memories,
            **kwargs,
        )
        if websearch:
            if user_input == "":
                if "primary_objective" in kwargs and "task" in kwargs:
                    search_string = f"Primary Objective: {kwargs['primary_objective']}\n\nTask: {kwargs['task']}"
            else:
                search_string = user_input
            if search_string != "":
                await self.websearch_agent(
                    user_input=search_string, depth=websearch_depth
                )
        try:
            # Workaround for non-threaded providers
            run_response = await self.agent.instruct(formatted_prompt, tokens=tokens)
            self.response = (
                run_response.result()
                if isinstance(run_response, Future)
                else run_response
            )
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
            self.response = await self.run(
                user_input=user_input,
                prompt=prompt,
                context_results=context_results,
                **kwargs,
            )

        # Handle commands if the prompt contains the {COMMANDS} placeholder
        # We handle command injection that DOESN'T allow command execution by using {command_list} in the prompt
        if "{COMMANDS}" in unformatted_prompt:
            execution_response = await self.execution_agent(
                execution_response=self.response,
                user_input=user_input,
                context_results=context_results,
                **kwargs,
            )
            return_response = ""
            if bool(self.agent.AUTONOMOUS_EXECUTION) == True:
                try:
                    self.response = json.loads(self.response)
                    if "response" in self.response:
                        return_response = self.response["response"]
                    if "commands" in self.response:
                        if self.response["commands"] != {}:
                            return_response += (
                                f"\n\nCommands Executed:\n{self.response['commands']}"
                            )
                    if execution_response:
                        return_response += (
                            f"\n\nCommand Execution Response:\n{execution_response}"
                        )
                except:
                    return_response = self.response
            else:
                return_response = f"{self.response}\n\n{execution_response}"
            self.response = return_response
        logging.info(f"Response: {self.response}")
        if self.response != "" and self.response != None:
            if disable_memory == False:
                try:
                    await self.memories.store_result(
                        input=user_input, result=self.response
                    )
                except:
                    pass
            if prompt == "Chat":
                self.agent.log_interaction(role="USER", message=user_input)
            else:
                self.agent.log_interaction(role="USER", message=formatted_prompt)
            self.agent.log_interaction(role=self.agent_name, message=self.response)

        if shots > 1:
            responses = [self.response]
            for shot in range(shots - 1):
                shot_response = await self.run(
                    user_input=user_input,
                    prompt=prompt,
                    context_results=context_results,
                    shots=shots - 1,
                    chain_name=chain_name,
                    step_number=step_number,
                    **kwargs,
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

    async def run_chain_step(
        self, step: dict = {}, chain_name="", user_input="", agent_override=""
    ):
        if step:
            if "prompt_type" in step:
                if agent_override != "":
                    self.agent_name = agent_override
                else:
                    self.agent_name = step["agent_name"]
                self.agent = Agent(self.agent_name)
                self.agent_commands = self.agent.get_commands_string()
                self.memories = self.agent.get_memories()
                prompt_type = step["prompt_type"]
                step_number = step["step"]
                if "prompt_name" in step["prompt"]:
                    prompt_name = step["prompt"]["prompt_name"]
                else:
                    prompt_name = ""
                args = self.get_step_content(
                    chain_name=chain_name,
                    prompt_content=step["prompt"],
                    user_input=user_input,
                    agent_name=self.agent_name,
                )
                if prompt_type == "Command":
                    return await self.agent.execute(
                        command_name=args["command_name"],
                        command_args=args,
                    )
                elif prompt_type == "Prompt":
                    result = await self.run(
                        user_input=user_input,
                        prompt=prompt_name,
                        chain_name=chain_name,
                        step_number=step_number,
                        **args,
                    )
                elif prompt_type == "Chain":
                    result = await self.run_chain(
                        chain_name=args["chain"],
                        user_input=args["input"],
                        agent_override=self.agent_name,
                        all_responses=False,
                    )
        if result:
            return result
        else:
            return None

    async def run_chain(
        self,
        chain_name,
        user_input=None,
        all_responses=True,
        agent_override="",
        from_step=1,
    ):
        chain = Chain()
        file_path = get_chain_responses_file_path(chain_name=chain_name)
        chain_data = chain.get_chain(chain_name=chain_name)
        if chain_data == {}:
            return f"Chain `{chain_name}` not found."
        logging.info(f"Running chain '{chain_name}'")
        responses = {}  # Create a dictionary to hold responses.
        last_response = ""
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
                    logging.info(
                        f"Running step {step_data['step']} with agent {step['agent_name']}."
                    )
                    step_response = await self.run_chain_step(
                        step=step_data,
                        chain_name=chain_name,
                        user_input=user_input,
                        agent_override=agent_override,
                    )  # Get the response of the current step.
                    step["response"] = step_response
                    last_response = step_response
                    responses[step_data["step"]] = step  # Store the response.
                    logging.info(f"Response: {step_response}")
                    # Write the responses to the json file.
                    dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with open(file_path, "w") as f:
                        json.dump(responses, f)
        if all_responses == True:
            return responses
        else:
            # Return only the last response in the chain.
            return last_response

    async def smart_instruct(
        self,
        user_input: str = "Write a tweet about AI.",
        shots: int = 3,
        learn_file: str = "",
        objective: str = None,
        **kwargs,
    ):
        answers = []
        # Do multi shots of prompt to get N different answers to be validated
        answers.append(
            await self.run(
                user_input=user_input,
                prompt="SmartInstruct-StepByStep"
                if objective == None
                else "SmartTask-StepByStep",
                context_results=6,
                websearch=True,
                websearch_depth=3,
                shots=shots,
                learn_file=learn_file,
                objective=objective,
                **kwargs,
            )
        )
        if shots > 1:
            for i in range(shots - 1):
                answers.append(
                    await self.run(
                        user_input=user_input,
                        prompt="SmartInstruct-StepByStep"
                        if objective == None
                        else "SmartTask-StepByStep",
                        context_results=6,
                        shots=shots,
                        objective=objective,
                        **kwargs,
                    )
                )
        answer_str = ""
        for i, answer in enumerate(answers):
            answer_str += f"Answer {i + 1}:\n{answer}\n\n"
        researcher = await self.run(
            user_input=answer_str,
            prompt="SmartInstruct-Researcher",
            shots=shots,
            **kwargs,
        )
        resolver = await self.run(
            user_input=researcher,
            prompt="SmartInstruct-Resolver",
            shots=shots,
            **kwargs,
        )
        execution_response = await self.run(
            user_input=f"{user_input}\nContext:\n{resolver}",
            prompt="instruct",
            **kwargs,
        )
        response = f"{resolver}\n\n{execution_response}"
        return response

    async def smart_chat(
        self,
        user_input: str = "Write a tweet about AI.",
        shots: int = 3,
        learn_file: str = "",
        **kwargs,
    ):
        answers = []
        answers.append(
            await self.run(
                user_input=user_input,
                prompt="SmartChat-StepByStep",
                context_results=6,
                websearch=True,
                websearch_depth=3,
                shots=shots,
                learn_file=learn_file,
                **kwargs,
            )
        )
        # Do multi shots of prompt to get N different answers to be validated
        if shots > 1:
            for i in range(shots - 1):
                answers.append(
                    await self.run(
                        user_input=user_input,
                        prompt="SmartChat-StepByStep",
                        context_results=6,
                        shots=shots,
                        **kwargs,
                    )
                )
        answer_str = ""
        for i, answer in enumerate(answers):
            answer_str += f"Answer {i + 1}:\n{answer}\n\n"
        researcher = await self.run(
            user_input=answer_str,
            prompt="SmartChat-Researcher",
            context_results=6,
            shots=shots,
            **kwargs,
        )
        resolver = await self.run(
            user_input=researcher,
            prompt="SmartChat-Resolver",
            context_results=6,
            shots=shots,
            **kwargs,
        )
        return resolver

    # Worker Sub-Agents
    async def validation_agent(
        self, user_input, execution_response, context_results, **kwargs
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
            execution_response = await self.run(
                user_input=user_input, context_results=context_results, **kwargs
            )
            return await self.validation_agent(
                user_input=user_input,
                execution_response=execution_response,
                context_results=context_results,
                **kwargs,
            )

    async def execution_agent(
        self, execution_response, user_input, context_results, **kwargs
    ):
        validated_response = await self.validation_agent(
            user_input=user_input,
            execution_response=execution_response,
            context_results=context_results,
            **kwargs,
        )
        if "commands" in validated_response:
            for command_name, command_args in validated_response["commands"].items():
                # Search for the command in the available_commands list, and if found, use the command's name attribute for execution
                if command_name is not None:
                    for available_command in self.agent.available_commands:
                        if command_name == available_command["friendly_name"]:
                            # Check if the command is a valid command in the self.avent.available_commands list
                            try:
                                if bool(self.agent.AUTONOMOUS_EXECUTION) == True:
                                    command_output = await self.agent.execute(
                                        command_name=command_name,
                                        command_args=command_args,
                                    )
                                else:
                                    command_output = create_command_suggestion_chain(
                                        agent_name=self.agent_name,
                                        command_name=command_name,
                                        command_args=command_args,
                                    )
                            except Exception as e:
                                logging.info("Command validation failed, retrying...")
                                validate_command = await self.run(
                                    user_input=user_input,
                                    prompt="ValidationFailed",
                                    command_name=command_name,
                                    command_args=command_args,
                                    command_output=e,
                                    context_results=context_results,
                                    **kwargs,
                                )
                                return await self.execution_agent(
                                    execution_response=validate_command,
                                    user_input=user_input,
                                    context_results=context_results,
                                    **kwargs,
                                )
                            logging.info(
                                f"Command {command_name} executed successfully with args {command_args}. Command Output: {command_output}"
                            )
                            response = f"\nExecuted Command:{command_name} with args {command_args}.\nCommand Output: {command_output}\n"
                            return response
                else:
                    if command_name == "None.":
                        return "\nNo commands were executed.\n"
                    else:
                        return f"\Command not recognized: `{command_name}`."
        else:
            return "\nNo commands were executed.\n"

    async def get_web_content(self, url):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(url)
                content = await page.content()

                # Scrape links and their titles
                links = await page.query_selector_all("a")
                link_list = []
                for link in links:
                    title = await page.evaluate("(link) => link.textContent", link)
                    href = await page.evaluate("(link) => link.href", link)
                    link_list.append((title, href))

                await browser.close()
                soup = BeautifulSoup(content, "html.parser")
                text_content = soup.get_text()
                text_content = " ".join(text_content.split())
                return text_content, link_list
        except:
            return None, None

    async def resursive_browsing(self, user_input, links):
        chunk_size = int(int(self.agent.MAX_TOKENS) / 2)
        try:
            words = links.split()
            links = [
                word for word in words if urlparse(word).scheme in ["http", "https"]
            ]
        except:
            links = links
        if links is not None:
            for link in links:
                if "href" in link:
                    try:
                        url = link["href"]
                    except:
                        url = link
                else:
                    url = link
                url = re.sub(r"^.*?(http)", r"http", url)
                # Check if url is an actual url
                if url.startswith("http"):
                    logging.info(f"Scraping: {url}")
                    if url not in self.browsed_links:
                        self.browsed_links.append(url)
                        (
                            collected_data,
                            link_list,
                        ) = await self.get_web_content(url=url)
                        # Split the collected data into agent max tokens / 2 character chunks
                        if collected_data is not None:
                            if len(collected_data) > 0:
                                chunks = [
                                    collected_data[i : i + chunk_size]
                                    for i in range(
                                        0,
                                        len(collected_data),
                                        chunk_size,
                                    )
                                ]
                                for chunk in chunks:
                                    summarized_content = await self.run(
                                        user_input=user_input,
                                        prompt="Summarize Web Content",
                                        link=url,
                                        chunk=chunk,
                                        disable_memory=True,
                                    )
                                    if not summarized_content.startswith("None"):
                                        try:
                                            await self.memories.store_result(
                                                input=user_input,
                                                result=summarized_content,
                                                external_source_name=url,
                                            )
                                        except:
                                            logging.info(
                                                f"Failed to store result for {url}. Moving on..."
                                            )
                        if link_list is not None:
                            if len(link_list) > 0:
                                if len(link_list) > 5:
                                    link_list = link_list[:3]
                                try:
                                    pick_a_link = await self.run(
                                        user_input=user_input,
                                        prompt="Pick-a-Link",
                                        links=link_list,
                                    )
                                    if not pick_a_link.startswith("None"):
                                        await self.resursive_browsing(
                                            user_input=user_input, links=pick_a_link
                                        )
                                except:
                                    logging.info(f"Issues reading {url}. Moving on...")

    async def websearch_agent(
        self,
        user_input: str = "What are the latest breakthroughs in AI?",
        depth: int = 3,
    ):
        results = await self.run(
            user_input=user_input, prompt="WebSearch", disable_memory=True
        )
        results = results.split("\n")
        for result in results:
            search_string = result.lstrip("0123456789. ")
            try:
                searx_server = self.agent.PROVIDER_SETTINGS["SEARXNG_INSTANCE_URL"]
            except:
                searx_server = ""
            try:
                links = await searxng(SEARXNG_INSTANCE_URL=searx_server).search(
                    query=search_string
                )
                if len(links) > depth:
                    links = links[:depth]
            except:
                links = None
            if links is not None:
                await self.resursive_browsing(user_input=user_input, links=links)
