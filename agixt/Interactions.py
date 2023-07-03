import re
import regex
import json
import time
import random
import requests
import logging
from datetime import datetime
from Agent import Agent
from Prompts import Prompts
from Embedding import get_tokens
from Chain import Chain
from urllib.parse import urlparse
from concurrent.futures import Future
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from agixtsdk import AGiXTSDK
from History import log_interaction
from typing import List

base_uri = "http://localhost:7437"
ApiClient = AGiXTSDK(base_uri=base_uri)
chain = Chain()
cp = Prompts()


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
                log_interaction(role="USER", message=user_input)
            else:
                log_interaction(role="USER", message=formatted_prompt)
            log_interaction(role=self.agent_name, message=self.response)

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
                                    command_output = (
                                        self.create_command_suggestion_chain(
                                            agent_name=self.agent_name,
                                            command_name=command_name,
                                            command_args=command_args,
                                        )
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

    async def search(self, query: str, searx_instance_url: str = "") -> List[str]:
        if searx_instance_url == "":
            try:  # SearXNG - List of these at https://searx.space/
                response = requests.get("https://searx.space/data/instances.json")
                data = json.loads(response.text)
                servers = list(data["instances"].keys())
                random_index = random.randint(0, len(servers) - 1)
                searx_instance_url = servers[random_index]
            except:  # Select default remote server that typically works if unable to get list.
                searx_instance_url = "https://search.us.projectsegfau.lt"
        server = searx_instance_url.rstrip("/")
        endpoint = f"{server}/search"
        try:
            response = requests.get(
                endpoint,
                params={
                    "q": query,
                    "language": "en",
                    "safesearch": 1,
                    "format": "json",
                },
            )
            results = response.json()
            summaries = [
                result["title"] + " - " + result["url"] for result in results["results"]
            ]
            return summaries
        except:
            # The SearXNG server is down or refusing connection, so we will use the default one.
            endpoint = "https://search.us.projectsegfau.lt/search"
            return await self.search(query=query, endpoint=endpoint)

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
                searx_instance_url = self.agent.PROVIDER_SETTINGS[
                    "SEARXNG_INSTANCE_URL"
                ]
            except:
                searx_instance_url = ""
            try:
                links = await self.search(
                    query=search_string, searx_instance_url=searx_instance_url
                )
                if len(links) > depth:
                    links = links[:depth]
            except:
                links = None
            if links is not None:
                await self.resursive_browsing(user_input=user_input, links=links)
