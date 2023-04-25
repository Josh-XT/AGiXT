import importlib
import secrets
import string
import argparse
import re
import spacy
from collections import deque
from typing import List, Dict
import chromadb
from chromadb.utils import embedding_functions
from Config import Config
from commands.web_requests import web_requests
from Commands import Commands
nlp = spacy.load("en_core_web_sm")
class AgentLLM:
    def __init__(self, agent_name: str = "default", primary_objective=None):
        self.CFG = Config(agent_name)
        self.primary_objective = self.CFG.OBJECTIVE if primary_objective == None else primary_objective
        self.initialize_task_list()
        self.commands = Commands(agent_name)
        self.available_commands = self.get_agent_commands()
        self.web_requests = web_requests()
        if self.CFG.AI_PROVIDER == "openai":
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(api_key=self.CFG.OPENAI_API_KEY)
        else:
            self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self.chroma_persist_dir = f"agents/{agent_name}/memories"
        self.chroma_client = chromadb.Client(
            settings=chromadb.config.Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.chroma_persist_dir,
            )
        )
        stripped_agent_name = "".join(c for c in agent_name if c in string.ascii_letters)
        self.collection = self.chroma_client.get_or_create_collection(
            name=str(stripped_agent_name).lower(),
            metadata={"hnsw:space": "cosine"},
            embedding_function=self.embedding_function,
        )
        ai_module = importlib.import_module(f"provider.{self.CFG.AI_PROVIDER}")
        self.ai_instance = ai_module.AIProvider()
        self.instruct = self.ai_instance.instruct
        self.agent_name = agent_name
        self.output_list = []
        self.stop_running_event = None

    def get_output_list(self):
        return self.output_list
    
    def get_agent_commands(self) -> List[str]:
        return self.commands.get_available_commands()

    def trim_context(self, context: List[str], max_tokens: int) -> List[str]:
        trimmed_context = []
        total_tokens = 0
        for item in context:
            item_tokens = len(item.split())  # Assuming words as tokens, adjust as needed
            if total_tokens + item_tokens <= max_tokens:
                trimmed_context.append(item)
                total_tokens += item_tokens
            else:
                break
        return trimmed_context

    def run(self, task: str, max_context_tokens: int = 500, long_term_access: bool = False, commands_enabled: bool = True):
        if self.CFG.NO_MEMORY:
            prompt = task
        else:
            self.CFG.log_interaction("USER", task)
            context = self.context_agent(query=task, top_results_num=3, long_term_access=long_term_access)
            context = self.trim_context(context, max_context_tokens)
            prompt = self.get_prompt_with_context(task=task, context=context)
        self.response = self.instruct(prompt)
        if not self.CFG.NO_MEMORY:
            self.store_result(task, self.response)
            self.CFG.log_interaction(self.agent_name, self.response)
        # Check if any commands are in the response and execute them with their arguments if so
        if commands_enabled:
            # Parse out everything after Commands: in self.response, each new line is a command
            commands = re.findall(r"Commands:(.*)", self.response, re.MULTILINE)
            if len(commands) > 0:
                response_parts = []
                for command in commands[0].split("\n"):
                    command = command.strip()
                    command_name, command_args = None, {}
                    # Extract command name and arguments using regex
                    command_regex = re.match(r'(\w+)\((.*)\)', command)
                    if command_regex:
                        command_name, args_str = command_regex.groups()
                        if args_str:
                            # Parse arguments string into a dictionary
                            command_args = dict((key.strip(), value.strip()) for key, value in (arg.split('=') for arg in args_str.split(',')))

                    # Search for the command in the available_commands list, and if found, use the command's name attribute for execution
                    if command_name is not None:
                        for available_command in self.available_commands:
                            if available_command["friendly_name"] == command_name:
                                command_name = available_command["name"]
                                break
                        response_parts.append(f"\n\n{self.execute_command(command_name, command_args)}")
                    else:
                        response_parts.append(f"\n\nCommand not recognized: {command}")
                self.response = self.response.replace(commands[0], "".join(response_parts))
        print(f"Response: {self.response}")
        return self.response

    def store_result(self, task_name: str, result: str):
        if result:
            result_id = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(64))
            if (len(self.collection.get(ids=[result_id], include=[])["ids"]) > 0):
                self.collection.update(ids=result_id, documents=result, metadatas={"task": task_name, "result": result})
            else:
                self.collection.add(ids=result_id, documents=result, metadatas={"task": task_name, "result": result})

    def context_agent(self, query: str, top_results_num: int, long_term_access: bool = False) -> List[str]:
        if long_term_access:
            interactions = self.CFG.memory["interactions"]
            context = [interaction["message"] for interaction in interactions[-top_results_num:]]
            context = self.chunk_content("\n\n".join(context))[-top_results_num:]
        else:
            count = self.collection.count()
            if count == 0:
                return []
            results = self.collection.query(query_texts=query, n_results=min(top_results_num, count), include=["metadatas"])
            context = [item["result"] for item in results["metadatas"][0]]
        return context

    def get_prompt_with_context(self, task: str, context: List[str]) -> str:
        context_str = "\n\n".join(context)
        prompt = f"Task: {task}\n\nContext: {context_str}\n\nResponse:"
        return prompt

    def chunk_content(self, content: str, max_length: int = 500) -> List[str]:
        content_chunks = []
        content_length = len(content)
        for i in range(0, content_length, max_length):
            chunk = content[i:i + max_length]
            content_chunks.append(chunk)
        return content_chunks

    def set_agent_name(self, agent_name):
        self.agent_name = agent_name

    def get_status(self):
        return not self.stop_running_event.is_set()

    def initialize_task_list(self):
        self.task_list = deque([])

    def update_output_list(self, output):
        print(self.CFG.save_task_output(self.agent_name, output, self.primary_objective))
        #self.output_list.append(output)

    def set_objective(self, new_objective):
        self.primary_objective = new_objective

    def task_creation_agent(self, result: Dict, task_description: str, task_list: List[str]) -> List[Dict]:
        prompt = f"""
        You are a task creation AI that uses the result of an execution agent to create new tasks with the following objective: {self.primary_objective},
        The last completed task has the result: {result}.
        This result was based on this task description: {task_description}. These are incomplete tasks: {', '.join(task_list)}.
        Based on the result, create new tasks to be completed by the AI system that do not overlap with incomplete tasks.
        Return the tasks as an array."""
        response = self.run(prompt, commands_enabled=False)
        new_tasks = response.split("\n") if "\n" in response else [response]
        return [{"task_name": task_name} for task_name in new_tasks]

    def prioritization_agent(self):
        task_names = [t["task_name"] for t in self.task_list]
        next_task_id = len(self.task_list) + 1
        prompt = f"""
        You are a task prioritization AI tasked with cleaning the formatting of and re-prioritizing the following tasks: {task_names}.
        Consider the ultimate objective of your team:{self.primary_objective}.
        Do not remove any tasks. Return the result as a numbered list, like:
        #. First task
        #. Second task
        Start the task list with number {next_task_id}."""
        response = self.run(prompt, commands_enabled=False)
        new_tasks = response.split("\n") if "\n" in response else [response]
        self.task_list = deque()
        for task_string in new_tasks:
            task_parts = task_string.strip().split(".", 1)
            if len(task_parts) == 2:
                task_id = task_parts[0].strip()
                task_name = task_parts[1].strip()
                self.task_list.append({"task_id": task_id, "task_name": task_name})

    def execution_agent(self, task: str, task_id: int) -> str:
        context = self.context_agent(query=self.primary_objective, top_results_num=5)
        prompt = f"""
        You are an AI who performs one task based on the following objective: {self.primary_objective}\n.
        Take into account these previously completed tasks: {context}\n.
        Your task: {task}\nResponse:"""
        return self.run(prompt)

    def run_task(self, stop_event):
        self.stop_running_event = stop_event
        while self.task_list and not stop_event.is_set():
            task = self.task_list.popleft()
            self.update_output(f"\nExecuting task {task['task_id']}: {task['task_name']}\n")
            result = self.execution_agent(task["task_name"], task["task_id"])
            self.update_output(f"\nTask Result:\n\n{result}\n")
            new_tasks = self.task_creation_agent({"data": result}, task["task_name"], [t["task_name"] for t in self.task_list])
            self.update_output(f"\nNew Tasks:\n\n{new_tasks}\n")
            for new_task in new_tasks:
                new_task.update({"task_id": len(self.task_list) + 1})
                self.task_list.append(new_task)
            self.prioritization_agent()
        print("All tasks completed or stopped.")

    def run_chain_step(self, agent_name, step_data):
        for prompt_type, prompt in step_data.items():
            if prompt_type == "instruction":
                self.run(prompt)
            elif prompt_type == "task":
                self.run_task(prompt)

    def run_chain(self, agent_name, chain_name):
        chain_data = self.CFG.get_steps(chain_name)
        for step_number, step_data in chain_data.items():
            self.run_chain_step(agent_name, step_data)

if __name__ == '__main__':
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
    agent.run(task=prompt, max_context_tokens=max_context_tokens, long_term_access=long_term_access)