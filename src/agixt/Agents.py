import re
import regex
import json
from AGiXT import AGiXT
from Commands import Commands
from Learning import Learning
from typing import List, Dict
from duckduckgo_search import ddg
from urllib.parse import urlparse


class Agents:
    def __init__(self, agent_name: str = "AGiXT"):
        self.agent_name = agent_name
        self.primary_objective = None
        self.commands = Commands(self.agent_name)
        self.available_commands = self.commands.get_available_commands()
        self.browsed_links = []

    # Worker Sub-Agents
    def validation_agent(self, task, execution_response, context_results, **kwargs):
        try:
            pattern = regex.compile(r"\{(?:[^{}]|(?R))*\}")
            cleaned_json = pattern.findall(execution_response)
            if len(cleaned_json) == 0:
                return False
            if isinstance(cleaned_json, list):
                cleaned_json = cleaned_json[0]
            response = json.loads(cleaned_json)
            return response
        except:
            print("INVALID JSON RESPONSE")
            print(execution_response)
            print("... Trying again.")
            if context_results != 0:
                context_results = context_results - 1
            else:
                context_results = 0
            execution_response = AGiXT(self.agent_name).run(
                task=task, context_results=context_results, **kwargs
            )
            return self.validation_agent(
                task, execution_response, context_results, **kwargs
            )

    def revalidation_agent(
        self,
        task,
        command_name,
        command_args,
        command_output,
        context_results,
        **kwargs,
    ):
        print(
            f"Command {command_name} did not execute as expected with args {command_args}. Trying again.."
        )
        revalidate = AGiXT(self.agent_name).run(
            task=task,
            prompt="ValidationFailed",
            command_name=command_name,
            command_args=command_args,
            command_output=command_output,
            **kwargs,
        )
        return self.execution_agent(revalidate, task, context_results, **kwargs)

    def execution_agent(self, execution_response, task, context_results, **kwargs):
        validated_response = self.validation_agent(
            task, execution_response, context_results, **kwargs
        )
        try:
            for command_name, command_args in validated_response["commands"].items():
                # Search for the command in the available_commands list, and if found, use the command's name attribute for execution
                if command_name is not None:
                    for available_command in self.available_commands:
                        if command_name in [
                            available_command["friendly_name"],
                            available_command["name"],
                        ]:
                            command_name = available_command["name"]
                            break
                    try:
                        command_output = self.commands.execute_command(
                            command_name, command_args
                        )
                        print("Running Command Execution Validation...")
                        validate_command = AGiXT(self.agent_name).run(
                            task=task,
                            prompt="Validation",
                            command_name=command_name,
                            command_args=command_args,
                            command_output=command_output,
                            **kwargs,
                        )
                    except:
                        return self.revalidation_agent(
                            task, command_name, command_args, command_output, **kwargs
                        )

                    if validate_command.startswith("Y"):
                        print(
                            f"Command {command_name} executed successfully with args {command_args}."
                        )
                        response = f"\nExecuted Command:{command_name} with args {command_args}.\nCommand Output: {command_output}\n"
                        return response
                    else:
                        return self.revalidation_agent(
                            task, command_name, command_args, command_output, **kwargs
                        )
                else:
                    if command_name == "None.":
                        return "\nNo commands were executed.\n"
                    else:
                        return f"\Command not recognized: {command_name} ."
        except:
            print("\nERROR IN EXECUTION_AGENT, validated_response:\n")
            print(validated_response)
            return "\nNo commands were executed.\n"

    def task_agent(
        self, result: Dict, task_description: str, task_list: List[str]
    ) -> List[Dict]:
        response = AGiXT(self.agent_name).run(
            task=self.primary_objective,
            prompt="task",
            result=result,
            task_description=task_description,
            tasks=", ".join(task_list),
        )

        lines = response.split("\n") if "\n" in response else [response]
        new_tasks = [
            re.sub(r"^.*?(\d)", r"\1", line)
            for line in lines
            if line.strip() and re.search(r"\d", line[:10])
        ] or [response]
        return [
            {"task_name": task_name} for task_name in new_tasks if task_name.strip()
        ]

    async def websearch_agent(
        self, task: str = "What are the latest breakthroughs in AI?", depth: int = 3
    ):
        async def resursive_browsing(self, task, links):
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
                        url = link["href"]
                    else:
                        url = link
                    url = re.sub(r"^.*?(http)", r"http", url)
                    # Check if url is an actual url
                    if url.startswith("http"):
                        print(f"Scraping: {url}")
                        if url not in self.browsed_links:
                            self.browsed_links.append(url)
                            collected_data, link_list = await Learning(
                                self.agent_name
                            ).read_website(url)
                            if link_list is not None:
                                if len(link_list) > 0:
                                    if len(link_list) > 5:
                                        link_list = link_list[:3]
                                    try:
                                        pick_a_link = AGiXT(self.agent_name).run(
                                            task=task,
                                            prompt="Pick-a-Link",
                                            links=link_list,
                                        )
                                        if not pick_a_link.startswith("None"):
                                            await resursive_browsing(task, pick_a_link)
                                    except:
                                        print(f"Issues reading {url}. Moving on...")

        results = AGiXT(self.agent_name).run(task=task, prompt="WebSearch")
        results = results.split("\n")
        for result in results:
            search_string = result.lstrip("0123456789. ")
            links = ddg(search_string, max_results=depth)
            if links is not None:
                await resursive_browsing(task, links)

    def instruction_agent(self, task, learn_file: str = "", **kwargs):
        if "task_name" in task:
            task = task["task_name"]
        resolver = AGiXT(self.agent_name).run(
            task=task,
            prompt="SmartInstruct-StepByStep",
            context_results=6,
            learn_file=learn_file,
            **kwargs,
        )
        execution_response = AGiXT(self.agent_name).run(
            task=task,
            prompt="SmartInstruct-Execution",
            previous_response=resolver,
            **kwargs,
        )
        return (
            f"RESPONSE:\n{resolver}\n\nCommand Execution Response{execution_response}"
        )
