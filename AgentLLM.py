import importlib
import secrets
import string
from typing import List
import chromadb
from chromadb.utils import embedding_functions
from Config import Config
from YamlMemory import YamlMemory
from commands.web_requests import web_requests
from Commands import Commands

class AgentLLM:
    def __init__(self):
        self.CFG = Config()
        self.commands = Commands()
        self.web_requests = web_requests()
        if self.CFG.AI_PROVIDER == "openai":
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(api_key=self.CFG.OPENAI_API_KEY)
        else:
            self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self.chroma_persist_dir = "memories"
        self.chroma_client = chromadb.Client(
            settings=chromadb.config.Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.chroma_persist_dir,
            )
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=str(self.CFG.AGENT_NAME).lower(),
            metadata={"hnsw:space": "cosine"},
            embedding_function=self.embedding_function,
        )
        ai_module = importlib.import_module(f"provider.{self.CFG.AI_PROVIDER}")
        self.ai_instance = ai_module.AIProvider()
        self.instruct = self.ai_instance.instruct
        self.yaml_memory = YamlMemory(self.CFG.AGENT_NAME)

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

    def run(self, task: str, max_context_tokens: int = 1000, long_term_access: bool = False):
        context = self.context_agent(query=task, top_results_num=5, long_term_access=long_term_access)
        context = self.trim_context(context, max_context_tokens)
        prompt = self.get_prompt_with_context(task=task, context=context)
        if self.CFG.COMMANDS_ENABLED:
            commands_prompt = self.commands.get_prompt()
            self.response = self.instruct(f"{commands_prompt}\n{prompt}")
        else:
            self.response = self.instruct(prompt)
        self.store_result(task, self.response)

        # Log the interaction in long term memory
        self.yaml_memory.log_interaction("USER", task)
        self.yaml_memory.log_interaction(self.CFG.AGENT_NAME, self.response)

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
        else:
            count = self.collection.count()
            if count == 0:
                return []
            results = self.collection.query(query_texts=query, n_results=min(top_results_num, count), include=["metadatas"])
            context = [item["result"] for item in results["metadatas"][0]]
        return context

    def get_prompt_with_context(self, task: str, context: List[str]) -> str:
        context_str = "\n\n".join(context)
        prompt = f"Context: {context_str}\n\nTask: {task}\n\nResponse:"
        return prompt

    def chunk_content(self, content: str, max_length: int = 500) -> List[str]:
        content_chunks = []
        content_length = len(content)
        for i in range(0, content_length, max_length):
            chunk = content[i:i + max_length]
            content_chunks.append(chunk)
        return content_chunks