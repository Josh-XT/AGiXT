import importlib
import secrets
import string
import argparse
import time
import re
from collections import deque
from typing import List, Dict
import chromadb
from chromadb.utils import embedding_functions
from Config import Config
from YamlMemory import YamlMemory
from commands.web_requests import web_requests
from Commands import Commands

class AgentLLM:
    def __init__(self, primary_objective=None, initial_task=None, agent_name: str = "default"):
        self.CFG = Config()
        self.primary_objective = self.CFG.OBJECTIVE if primary_objective == None else primary_objective
        self.initial_task = self.CFG.INITIAL_TASK if initial_task == None else initial_task
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
        self.yaml_memory = YamlMemory(agent_name)
        self.agent_name = agent_name
        self.output_list = []
        self.running = False

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
        if not self.CFG.NO_MEMORY:
            self.yaml_memory.log_interaction("USER", task)
            context = self.context_agent(query=task, top_results_num=3, long_term_access=long_term_access)
            context = self.trim_context(context, max_context_tokens)
            prompt = self.get_prompt_with_context(task=task, context=context)
        else:
            prompt = task
        self.response = self.instruct(prompt)
        if self.CFG.NO_MEMORY:
            self.store_result(task, self.response)
            self.yaml_memory.log_interaction(self.agent_name, self.response)
        print(f"Response: {self.response}")
        return self.response

    def store_result(self, task_name: str, result: str):
        result_id = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(64))
        if (len(self.collection.get(ids=[result_id], include=[])["ids"]) > 0):
            self.collection.update(ids=result_id, documents=result, metadatas={"task": task_name, "result": result})
        else:
            self.collection.add(ids=result_id, documents=result, metadatas={"task": task_name, "result": result})

    def context_agent(self, query: str, top_results_num: int, long_term_access: bool) -> List[str]:
        if long_term_access:
            interactions = self.yaml_memory.memory["interactions"]
            context = [interaction["message"] for interaction in interactions[-top_results_num:]]
            context = self.chunk_content("\n\n".join(context))[:top_results_num]
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
        return self.running

    def initialize_task_list(self):
        self.task_list = deque([])

    def display_objective_and_initial_task(self):
        self.output_list.append(f"Objective: {self.primary_objective}")
        self.output_list.append(f"Initial task: {self.initial_task}")
        print("\033[94m\033[1m" + "\n*****OBJECTIVE*****\n" + "\033[0m\033[0m")
        print(f"{self.primary_objective}")
        print("\033[93m\033[1m" + "\nInitial task:" + "\033[0m\033[0m" + f" {self.initial_task}")

    def add_initial_task(self):
        self.task_list.append({"task_id": 1, "task_name": self.initial_task})

    def set_objective(self, new_objective):
        self.primary_objective = new_objective

    def task_creation_agent(self, objective: str, result: Dict, task_description: str, task_list: List[str]):
        prompt = self.CFG.TASK_PROMPT
        prompt = prompt.replace("{objective}", objective)
        prompt = prompt.replace("{result}", str(result))
        prompt = prompt.replace("{task_description}", task_description)
        prompt = prompt.replace("{tasks}", ", ".join(task_list))
        response = self.run(prompt, commands_enabled=False)
        self.output_list.append(f"\n\nTask creation agent response:\n\n{response}")
        if response is None:
            return []  # Return an empty list when the response is None
        new_tasks = response.split("\n") if "\n" in response else [response]
        return [{"task_name": task_name} for task_name in new_tasks]

    def prioritization_agent(self, this_task_id: int = 1):
        task_names = [t["task_name"] for t in self.task_list]
        next_task_id = this_task_id + 1
        prompt = self.CFG.PRIORITY_PROMPT
        prompt = prompt.replace("{objective}", self.primary_objective)
        prompt = prompt.replace("{next_task_id}", str(next_task_id))
        prompt = prompt.replace("{task_names}", ", ".join(task_names))
        response = self.run(prompt, commands_enabled=False)
        self.output_list.append(f"Prioritization agent response: {response}")
        new_tasks = response.split("\n") if "\n" in response else [response]
        self.task_list = deque()
        for task_string in new_tasks:
            task_parts = task_string.strip().split(".", 1)
            if len(task_parts) == 2:
                task_id = task_parts[0].strip()
                task_name = task_parts[1].strip()
                self.task_list.append({"task_id": task_id, "task_name": task_name})
        self.display_task_list()

    def display_task_list(self):
        self.output_list.append(f"Task list:\n\n{self.task_list}")
        print("\033[95m\033[1m" + "\n*****TASK LIST*****\n" + "\033[0m\033[0m")
        for task in self.task_list:
            print(f"{task['task_id']}. {task['task_name']}")

    def execution_agent(self, objective, task, task_id, context=None):
        prompt = self.CFG.EXECUTION_PROMPT
        prompt = prompt.replace("{objective}", objective)
        prompt = prompt.replace("{task}", task)
        # Get all friendly names in commands into an array
        friendly_names = []
        self.commands = Commands(self.agent_name)
        self.available_commands = self.get_agent_commands()
        print("\033[92m\033[1m" + "\n*****COMMANDS*****\n" + "\033[0m\033[0m")
        print(self.available_commands)
        if self.commands is not None:
            for command in self.available_commands:
                if command["enabled"] != False:
                    friendly_names.append(f"{command['friendly_name']} - {command['name']}({command['args']})")
            prompt = prompt.replace("{COMMANDS}", "\n".join(friendly_names))
        if context is not None:
            context = list(context)  # Convert set to list
        prompt = prompt.replace("{context}", str(context))
        print("\033[92m\033[1m" + "\n*****PROMPT*****\n" + "\033[0m\033[0m")
        print(prompt)
        if task_id == 0:
            self.response = self.run(prompt, commands_enabled=False)
        else:
            self.response = self.run(prompt)
        print("\033[91m\033[1m" + "\n*****EXECUTION AGENT*****\n" + "\033[0m\033[0m")
        print(f"{task_id}: {task}")
        print("\033[93m\033[1m" + "\n*****RESPONSE*****\n" + "\033[0m\033[0m")
        print(self.response)
        self.output_list.append(f"Execution agent response:\n\n{self.response}")
        print(self.output_list)
        return self.response

    def display_result(self, task):
        self.display_task_list()
        self.output_list.append(f"Task:\n\n{task['task_id']}: {task['task_name']}")
        self.output_list.append(f"Result:\n\n{self.response}")
        print("\033[92m\033[1m" + "\n*****NEXT TASK*****\n" + "\033[0m\033[0m")
        print(f"{task['task_id']}: {task['task_name']}")
        print("\033[93m\033[1m" + "\n*****RESULT*****\n" + "\033[0m\033[0m")
        print(self.response)

    def execute_next_task(self):
        if self.task_list:
            task = self.task_list.popleft()
        else:
            task = {"task_id": 0, "task_name": self.initial_task}
        this_task_id = task["task_id"]
        if type(this_task_id) != int:
            this_task_id = ''.join(re.findall(r'\d+', this_task_id))
            try:
                this_task_id = int(this_task_id)
            except:
                this_task_id = 2
        this_task_name = task["task_name"]
        if this_task_name == "":
            return self.execute_next_task()
        self.response = self.execution_agent(self.primary_objective, this_task_name, this_task_id)
        new_tasks = self.task_creation_agent(
            self.primary_objective,
            { "data": self.response },
            this_task_name,
            [t["task_name"] for t in self.task_list],
        )
        task_id_counter = this_task_id
        for new_task in new_tasks:
            task_id_counter += 1
            new_task.update({"task_id": task_id_counter})
            self.task_list.append(new_task)
        self.prioritization_agent(this_task_id)
        return task

    def get_output(self):
        return self.output_list

    def stop_running(self):
        self.running = False

    def run_task(self):  # Main loop
        # Add the first task
        task = self.primary_objective
        self.add_initial_task()
        self.running = True
        while self.running:
            task = self.execute_next_task()
            self.display_result(task)
            if not self.task_list:
                self.output_list.append(f"\n\nAll tasks complete.")
                print("\033[91m\033[1m" + "\n*****ALL TASKS COMPLETE*****\n" + "\033[0m\033[0m")
                break
            time.sleep(0.5)  # Sleep before checking the task list again

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