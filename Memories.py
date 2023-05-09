import string
import chromadb
import secrets
from typing import List, Dict
from chromadb.utils import embedding_functions
from Config.Agent import Agent


class Memories:
    def __init__(self, AGENT_NAME: str = "Agent-LLM", nlp=None):
        self.AGENT_NAME = AGENT_NAME
        self.CFG = Agent(self.AGENT_NAME)
        self.nlp = nlp
        if self.CFG.AI_PROVIDER == "openai":
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=self.CFG.AGENT_CONFIG["settings"]["OPENAI_API_KEY"],
            )
        else:
            self.embedding_function = (
                embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
            )
        self.chroma_persist_dir = f"agents/{self.AGENT_NAME}/memories"
        self.chroma_client = chromadb.Client(
            settings=chromadb.config.Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.chroma_persist_dir,
            )
        )
        stripped_agent_name = "".join(
            c for c in self.AGENT_NAME if c in string.ascii_letters
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=str(stripped_agent_name).lower(),
            metadata={"hnsw:space": "cosine"},
            embedding_function=self.embedding_function,
        )

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
        max_tokens: int = 128,
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
            item_tokens = len(self.nlp(item))
            if total_tokens + item_tokens <= max_tokens:
                trimmed_context.append(item)
                total_tokens += item_tokens
            else:
                break
        return "\n".join(trimmed_context)

    def chunk_content(self, content: str, max_length: int = 128) -> List[str]:
        content_chunks = []
        doc = self.nlp(content)
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
