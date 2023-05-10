import string
import chromadb
import secrets
from typing import List, Dict
from chromadb.utils import embedding_functions
import spacy
from spacy.cli import download


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
        if self.CFG.AI_PROVIDER == "openai":
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=self.CFG.AGENT_CONFIG["settings"]["OPENAI_API_KEY"],
            )
        else:
            self.embedding_function = (
                embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-mpnet-base-v2"
                )
            )
        self.chroma_persist_dir = f"agents/{self.AGENT_NAME}/memories"
        self.chroma_client = chromadb.Client(
            settings=chromadb.config.Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.chroma_persist_dir,
            )
        )
        collection_name = "memories"
        try:
            self.collection = self.chroma_client.get_collection(
                name=collection_name, embedding_function=self.embedding_function
            )
            print(f"Collection {collection_name} found.")
        except ValueError:
            print(f"Collection {collection_name} does not exist. Creating it...")
            self.collection = self.chroma_client.create_collection(
                name=collection_name, embedding_function=self.embedding_function
            )
            print(f"Collection {collection_name} created successfully.")

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
        long_term_access: bool = False,
        max_tokens: int = 180,
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

    def chunk_content(self, content: str, max_length: int = 180) -> List[str]:
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
