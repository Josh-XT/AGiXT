import secrets
import string
import argparse
import re
import spacy
from collections import deque
from typing import List, Dict
import chromadb
from chromadb.utils import embedding_functions
from Config.Agent import Agent
from commands.web_requests import web_requests
from Commands import Commands
import json
from json.decoder import JSONDecodeError
import spacy
from spacy.cli import download
from CustomPrompt import CustomPrompt

try:
    nlp = spacy.load("en_core_web_sm")
except:
    print("Downloading spacy model...")
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")


class AgentLLM:
    def __init__(self, agent_name: str = "AgentLLM", primary_objective=None):
        self.CFG = Agent(agent_name)
        self.primary_objective = primary_objective
        self.task_list = deque([])
        self.commands = Commands(agent_name)
        self.available_commands = self.commands.get_available_commands()
        self.web_requests = web_requests()
        if self.CFG.AI_PROVIDER == "openai":
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=self.CFG.AGENT_CONFIG["settings"]["OPENAI_API_KEY"],
            )
        else:
            self.embedding_function = (
                embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="distilbert-base-uncased"
                )
            )
        self.chroma_persist_dir = f"agents/{agent_name}/memories"
        self.chroma_client = chromadb.Client(
            settings=chromadb.config.Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.chroma_persist_dir,
            )
        )
        stripped_agent_name = "".join(
            c for c in agent_name if c in string.ascii_letters
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=str(stripped_agent_name).lower(),
            metadata={"hnsw:space": "cosine"},
            embedding_function=self.embedding_function,
        )
        self.agent_name = agent_name
        self.agent_config = self.CFG.load_agent_config(self.agent_name)
        self.output_list = []
        self.stop_running_event = None

    def get_output_list(self):
        return self.output_list

    def get_commands_string(self):
        if len(self.available_commands) == 0:
            return "No commands."

        enabled_commands = filter(
            lambda command: command.get("enabled", True), self.available_commands
        )

        friendly_names = map(
            lambda command: f"{command['friendly_name']} - {command['name']}({command['args']})",
            enabled_commands,
        )
        return "\n".join(friendly_names)

    def run(
        self,
        task: str,
        max_context_tokens: int = 500,
        long_term_access: bool = False,
        commands_enabled: bool = True,
        prompt: str = "",
        **kwargs,
    ):
        cp = CustomPrompt()
        if prompt == "":
            prompt = task
        elif prompt in ["execute", "task", "priority", "instruct"]:
            prompt = cp.get_model_prompt(prompt_name=prompt, model=self.CFG.AI_MODEL)
        else:
            prompt = CustomPrompt().get_prompt(prompt)

        context = self.context_agent(
            query=task,
            top_results_num=3,
            long_term_access=long_term_access,
            max_tokens=max_context_tokens,
        )
        formatted_prompt = prompt.format(
            task=task,
            agent_name=self.agent_name,
            COMMANDS=self.get_commands_string(),
            context=context,
            objective=self.primary_objective,
            **kwargs,
        )
        self.CFG.log_interaction("USER", task)
        self.response = self.CFG.instruct(formatted_prompt)
        if not self.CFG.NO_MEMORY:
            self.store_result(task, self.response)
            self.CFG.log_interaction(self.agent_name, self.response)
        # Check if any commands are in the response and execute them with their arguments if so
        if commands_enabled:
            # Parse out everything after Commands: in self.response, each new line is a command
            commands = re.findall(
                r"(?i)Commands:[\n]*(.*)", f"{self.response}", re.DOTALL
            )
            if len(commands) > 0:
                response_parts = []
                for command in commands[0].split("\n"):
                    command = command.strip()
                    # Check if the command starts with a number and strip out everything until the first letter
                    if command and command[0].isdigit():
                        first_letter = re.search(r"[a-zA-Z]", command)
                        if first_letter:
                            command = command[first_letter.start() :]
                    command_name, command_args = None, {}
                    # Extract command name and arguments using regex
                    command_regex = re.search(r"(\w+)\((.*)\)", command)
                    if command_regex:
                        command_name, args_str = command_regex.groups()
                        if args_str:
                            # Parse arguments string into a dictionary
                            args_str = args_str.replace("'", '"')
                            args_str = args_str.replace("None", "null")
                            try:
                                command_args = json.loads(args_str)
                            except JSONDecodeError as e:
                                # error parsing args, send command_name to None so trying to execute command won't crash
                                command_name = None
                                print(f"Error: {e}")

                    # Search for the command in the available_commands list, and if found, use the command's name attribute for execution
                    if command_name is not None:
                        for available_command in self.available_commands:
                            if available_command["friendly_name"] == command_name:
                                command_name = available_command["name"]
                                break
                        response_parts.append(
                            f"\n\n{self.commands.execute_command(command_name, command_args)}"
                        )
                    else:
                        if command == "None.":
                            response_parts.append(f"\n\nNo commands were executed.")
                        else:
                            response_parts.append(
                                f"\n\nCommand not recognized: {command}"
                            )
                self.response = self.response.replace(
                    commands[0], "".join(response_parts)
                )
        print(f"Response: {self.response}")
        return self.response

    def store_result(self, task_name: str, result: str):
        if result:
            result_id = "".join(
                secrets.choice(string.ascii_lowercase + string.digits)
                for _ in range(64)
            )
            if len(self.collection.get(ids=[result_id], include=[])["ids"]) > 0:
                self.collection.update(
                    ids=result_id,
                    documents=result,
                    metadatas={"task": task_name, "result": result},
                )
            else:
                self.collection.add(
                    ids=result_id,
                    documents=result,
                    metadatas={"task": task_name, "result": result},
                )

    def context_agent(
        self,
        query: str,
        top_results_num: int,
        long_term_access: bool = False,
        max_tokens: int = 500,
    ) -> List[str]:
        if long_term_access:
            interactions = self.CFG.memory["interactions"]
            context = [
                interaction["message"]
                for interaction in interactions[-top_results_num:]
            ]
            context = self.chunk_content("\n\n".join(context))[-top_results_num:]
        else:
            count = self.collection.count()
            if count == 0:
                return []
            results = self.collection.query(
                query_texts=query,
                n_results=min(top_results_num, count),
                include=["metadatas"],
            )
            context = [item["result"] for item in results["metadatas"][0]]
        trimmed_context = []
        total_tokens = 0
        for item in context:
            item_tokens = len(nlp(item))
            if total_tokens + item_tokens <= max_tokens:
                trimmed_context.append(item)
                total_tokens += item_tokens
            else:
                break
        return "\n".join(trimmed_context)

    def chunk_content(self, content: str, max_length: int = 500) -> List[str]:
        content_chunks = []
        doc = nlp(content)
        length = 0
        chunk = []
        for sent in doc.sents:
            if length + len(sent) <= max_length:
                chunk.append(sent.text)
                length += len(sent)
            else:
                content_chunks.append(" ".join(chunk))
                chunk = [sent.text]
                length = len(sent)
        if chunk:
            content_chunks.append(" ".join(chunk))
        return content_chunks

    def get_status(self):
        try:
            return not self.stop_running_event.is_set()
        except:
            return False

    def update_output_list(self, output):
        print(
            self.CFG.save_task_output(self.agent_name, output, self.primary_objective)
        )

    def task_creation_agent(
        self, result: Dict, task_description: str, task_list: List[str]
    ) -> List[Dict]:
        response = self.run(
            task=self.primary_objective,
            commands_enabled=False,
            prompt="task",
            objective=self.primary_objective,
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
        return [{"task_name": task_name} for task_name in new_tasks]

    def prioritization_agent(self):
        task_names = [t["task_name"] for t in self.task_list]
        next_task_id = len(self.task_list) + 1

        response = self.run(
            task=self.primary_objective,
            commands_enabled=False,
            prompt="priority",
            objective=self.primary_objective,
            tasks=", ".join(task_names),
            next_task_id=next_task_id,
        )

        lines = response.split("\n") if "\n" in response else [response]
        new_tasks = [
            re.sub(r"^.*?(\d)", r"\1", line)
            for line in lines
            if line.strip() and re.search(r"\d", line[:10])
        ] or [response]
        self.task_list = deque()
        for task_string in new_tasks:
            task_parts = task_string.strip().split(".", 1)
            if len(task_parts) == 2:
                task_id = task_parts[0].strip()
                task_name = task_parts[1].strip()
                self.task_list.append({"task_id": task_id, "task_name": task_name})

    def run_task(self, stop_event, objective):
        self.primary_objective = objective
        self.update_output_list(
            f"Starting task with objective: {self.primary_objective}.\n\n"
        )
        if len(self.task_list) == 0:
            self.task_list.append({"task_id": 1, "task_name": "Develop a task list."})
        self.stop_running_event = stop_event
        while not stop_event.is_set():
            if self.task_list == []:
                break
            if len(self.task_list) > 0:
                task = self.task_list.popleft()
            self.update_output_list(
                f"\nExecuting task {task['task_id']}: {task['task_name']}\n"
            )
            result = self.run(task=task["task_name"], prompt="execute")
            self.update_output_list(f"\nTask Result:\n\n{result}\n")
            new_tasks = self.task_creation_agent(
                {"data": result},
                task["task_name"],
                [t["task_name"] for t in self.task_list],
            )
            self.update_output_list(f"\nNew Tasks:\n\n{new_tasks}\n")
            for new_task in new_tasks:
                new_task.update({"task_id": len(self.task_list) + 1})
                self.task_list.append(new_task)
            self.prioritization_agent()
        self.update_output_list("All tasks completed or stopped.")

    def run_chain_step(self, step_data_list):
        for step_data in step_data_list:
            for prompt_type, prompt in step_data.items():
                if prompt_type == "instruction":
                    self.run(prompt)
                elif prompt_type == "task":
                    self.run_task(prompt)
                elif prompt_type == "command":
                    command = prompt.strip()
                    command_name, command_args = None, {}
                    # Extract command name and arguments using regex
                    command_regex = re.search(r"(\w+)\((.*)\)", command)
                    if command_regex:
                        command_name, args_str = command_regex.groups()
                        if args_str:
                            # Parse arguments string into a dictionary
                            args_str = args_str.replace("'", '"')
                            args_str = args_str.replace("None", "null")
                            try:
                                command_args = json.loads(args_str)
                            except JSONDecodeError as e:
                                # error parsing args, send command_name to None so trying to execute command won't crash
                                command_name = None
                                print(f"Error: {e}")

                    # Search for the command in the available_commands list, and if found, use the command's name attribute for execution
                    if command_name is not None:
                        for available_command in self.available_commands:
                            if available_command["friendly_name"] == command_name:
                                command_name = available_command["name"]
                                break
                        self.commands.execute_command(command_name, command_args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, default="What is the weather like today?")
    parser.add_argument("--max_context_tokens", type=str, default="500")
    parser.add_argument("--long_term_access", type=bool, default=False)
    args = parser.parse_args()
    prompt = args.prompt
    max_context_tokens = int(args.max_context_tokens)
    long_term_access = args.long_term_access

    # Run AgentLLM
    agent = AgentLLM()
    agent.run(
        task=prompt,
        max_context_tokens=max_context_tokens,
        long_term_access=long_term_access,
    )
