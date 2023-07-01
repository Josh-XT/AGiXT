import re
import regex
import json
import time
from datetime import datetime
from Agent import Agent
from Prompts import Prompts
from Embedding import get_tokens
from extensions.searxng import searxng
from Chain import (
    Chain,
    get_chain_responses_file_path,
    create_command_suggestion_chain,
    get_step_response,
)
from urllib.parse import urlparse
import logging
from concurrent.futures import Future
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from agixtsdk import AGiXTSDK

base_uri = "http://localhost:7437"
ApiClient = AGiXTSDK(base_uri=base_uri)


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
                            step_response = get_step_response(
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
                    step_response = get_step_response(
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
                        step_response = get_step_response(
                            chain_name=chain_name, step_number=step_number
                        )
                        # replace the {STEPx} with the response
                        value = value.replace(f"{{STEP{step_number}}}", step_response)
                        kwargs[arg] = value
            except:
                logging.info("No args to replace.")
            if "{STEP" in prompt:
                step_response = get_step_response(
                    chain_name=chain_name, step_number=step_number
                )
                prompt = prompt.replace(f"{{STEP{step_number}}}", step_response)
            if "{STEP" in user_input:
                step_response = get_step_response(
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
        formatted_prompt = self.custom_format(
            string=prompt,
            user_input=user_input,
            agent_name=self.agent_name,
            COMMANDS=self.agent_commands,
            context=context,
            command_list=command_list,
            date=datetime.now().strftime("%B %d, %Y %I:%M %p"),
            working_directory=working_directory,
            helper_agent_name=helper_agent_name,
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
                learning_file = ApiClient.learn_file(file_path=learn_file)
            except:
                return "Failed to read file."
            if learning_file == False:
                return "Failed to read file."
        if websearch:
            if user_input == "":
                if "primary_objective" in kwargs and "task" in kwargs:
                    search_string = f"Primary Objective: {kwargs['primary_objective']}\n\nTask: {kwargs['task']}"
                else:
                    search_string = ""
            else:
                search_string = user_input
            if search_string != "":
                await self.websearch_agent(
                    user_input=search_string, depth=websearch_depth
                )
        formatted_prompt, unformatted_prompt, tokens = await self.format_prompt(
            user_input=user_input,
            top_results=context_results,
            prompt=prompt,
            chain_name=chain_name,
            step_number=step_number,
            memories=self.memories,
            **kwargs,
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
                shot_response = ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name=prompt,
                    prompt_args={
                        "chain_name": chain_name,
                        "step_number": step_number,
                        "user_input": user_input,
                        "context_results": context_results,
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
                    result = ApiClient.prompt_agent(
                        agent_name=self.agent_name,
                        prompt_name=prompt_name,
                        prompt_args={
                            "chain_name": chain_name,
                            "step_number": step_number,
                            "user_input": user_input,
                            **args,
                        },
                    )
                elif prompt_type == "Chain":
                    result = ApiClient.run_chain(
                        chain_name=args["chain"],
                        user_input=args["input"],
                        agent_name=self.agent_name,
                        all_responses=False,
                        from_step=1,
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
            execution_response = ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="JSONFormatter",
                prompt_args={
                    "user_input": user_input,
                    "context_results": context_results,
                    **kwargs,
                },
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
                                validate_command = ApiClient.prompt_agent(
                                    agent_name=self.agent_name,
                                    prompt_name="ValidationFailed",
                                    prompt_args={
                                        "command_name": command_name,
                                        "command_args": command_args,
                                        "command_output": e,
                                        "user_input": user_input,
                                        "context_results": context_results,
                                        **kwargs,
                                    },
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
                                tokens = get_tokens(collected_data)
                                chunks = [
                                    collected_data[i : i + chunk_size]
                                    for i in range(
                                        0,
                                        int(tokens),
                                        chunk_size,
                                    )
                                ]
                                for chunk in chunks:
                                    summarized_content = ApiClient.prompt_agent(
                                        agent_name=self.agent_name,
                                        prompt_name="Summarize Web Content",
                                        prompt_args={
                                            "link": url,
                                            "chunk": chunk,
                                            "disable_memory": True,
                                            "user_input": user_input,
                                        },
                                    )
                                    if not summarized_content.startswith("None"):
                                        await self.memories.store_result(
                                            input=user_input,
                                            result=summarized_content,
                                            external_source_name=url,
                                        )
                        if link_list is not None:
                            if len(link_list) > 0:
                                if len(link_list) > 5:
                                    link_list = link_list[:3]
                                try:
                                    pick_a_link = ApiClient.prompt_agent(
                                        agent_name=self.agent_name,
                                        prompt_name="Pick-a-Link",
                                        prompt_args={
                                            "links": link_list,
                                            "disable_memory": True,
                                            "user_input": user_input,
                                        },
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
        results = ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="WebSearch",
            prompt_args={
                "user_input": user_input,
                "disable_memory": True,
            },
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
