import string
import chromadb
import secrets
from typing import List
import spacy
from spacy.cli import download
from Embedding import Embedding


class Memories:
    def __init__(self, AGENT_NAME: str = "Agent-LLM", AgentConfig=None):
        self.AGENT_NAME = AGENT_NAME
        self.CFG = AgentConfig
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except:
            print("Downloading spacy model...")
            download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")
        self.embedding_function, self.chunk_size = Embedding(embedder=self.CFG.EMBEDDER)
        self.chroma_persist_dir = f"agents/{self.AGENT_NAME}/memories"
        self.chroma_client = chromadb.Client(
            settings=chromadb.config.Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.chroma_persist_dir,
            )
        )
        try:
            self.collection = self.chroma_client.get_collection(
                name="memories", embedding_function=self.embedding_function
            )
            print(f"Memories for {self.AGENT_NAME} found.")
        except ValueError:
            print(f"Memories for {self.AGENT_NAME} do not exist. Creating...")
            self.collection = self.chroma_client.create_collection(
                name="memories", embedding_function=self.embedding_function
            )
            print(f"Memories for {self.AGENT_NAME} created successfully.")

    def store(self, textdata, metadata, ids):
        """
        Stores new textdata, username, and ids in the ChromaDB collection.

        Args:
            textdata: list of strings, the text data to store.
            username: list of strings, the usernames associated with the text data.
            ids: list of strings or ints, the unique IDs associated with the text data.

        Returns:
            None.
        """
        # Store the new entry in the collection.
        self.collection.add(documents=textdata, metadatas=metadata, ids=ids)
        self.chroma_client.persist()

    def retrieve(self, query_text, name, chunk_type):
        metadata = {"name": name, "type": chunk_type}
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=3,
                where=metadata,
                include=["documents", "distances", "metadatas"],
            )
        except (
            chromadb.errors.NoDatapointsException,
            chromadb.errors.NotEnoughElementsException,
        ) as e:
            # Print the error message
            print(f"Error: {e}")
            # Return an empty list if no results are found or if there are not enough elements
            results = []

        # print(f"Generated results: {results}")
        return results

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
    ) -> List[str]:
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
            if total_tokens + item_tokens <= self.chunk_size:
                trimmed_context.append(item)
                total_tokens += item_tokens
            else:
                break
        return "\n".join(trimmed_context)

    def chunk_content(self, content: str) -> List[str]:
        content_chunks = []
        doc = self.nlp(content)
        length = 0
        chunk = []
        for sent in doc.sents:
            if length + len(sent) <= self.chunk_size:
                chunk.append(sent.text)
                length += len(sent)
            else:
                content_chunks.append(" ".join(chunk))
                chunk = [sent.text]
                length = len(sent)
        if chunk:
            content_chunks.append(" ".join(chunk))
        return content_chunks
