import logging
import os
import asyncio
import sys
import json
import time
import spacy
import chromadb
from chromadb.config import Settings
from chromadb.api.types import QueryResult
from numpy import array, linalg, ndarray
from hashlib import sha256
from Providers import Providers
from datetime import datetime
from collections import Counter
from typing import List
from Globals import getenv, DEFAULT_USER
from textacy.extract.keyterms import textrank

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def nlp(text):
    try:
        sp = spacy.load("en_core_web_sm")
    except:
        spacy.cli.download("en_core_web_sm")
        sp = spacy.load("en_core_web_sm")
    sp.max_length = 99999999999999999999999
    return sp(text)


def extract_keywords(doc=None, text="", limit=10):
    if not doc:
        doc = nlp(text)
    return [k for k, s in textrank(doc, topn=limit)]


def snake(old_str: str = ""):
    if not old_str:
        return ""
    if " " in old_str:
        old_str = old_str.replace(" ", "")
    if "@" in old_str:
        old_str = old_str.replace("@", "_")
    if "." in old_str:
        old_str = old_str.replace(".", "_")
    if "-" in old_str:
        old_str = old_str.replace("-", "_")
    snake_str = ""
    for i, char in enumerate(old_str):
        if char.isupper():
            if i != 0 and old_str[i - 1].islower():
                snake_str += "_"
            if i != len(old_str) - 1 and old_str[i + 1].islower():
                snake_str += "_"
        snake_str += char.lower()
    snake_str = snake_str.strip("_")
    return snake_str


def compute_similarity_scores(embedding: ndarray, embedding_array: ndarray) -> ndarray:
    query_norm = linalg.norm(embedding)
    collection_norm = linalg.norm(embedding_array, axis=1)
    valid_indices = (query_norm != 0) & (collection_norm != 0)
    similarity_scores = array([-1.0] * embedding_array.shape[0])

    if valid_indices.any():
        similarity_scores[valid_indices] = embedding.dot(
            embedding_array[valid_indices].T
        ) / (query_norm * collection_norm[valid_indices])
    else:
        raise ValueError(f"Invalid vectors: {embedding_array} or {embedding}")
    return similarity_scores


def query_results_to_records(results: "QueryResult"):
    try:
        if isinstance(results["ids"][0], str):
            for k, v in results.items():
                results[k] = [v]
    except IndexError:
        return []
    memory_records = [
        {
            "external_source_name": metadata["external_source_name"],
            "id": metadata["id"],
            "description": metadata["description"],
            "text": document,
            "embedding": embedding,
            "additional_metadata": metadata["additional_metadata"],
            "key": id,
            "timestamp": metadata["timestamp"],
        }
        for id, document, embedding, metadata in zip(
            results["ids"][0],
            results["documents"][0],
            results["embeddings"][0],
            results["metadatas"][0],
        )
    ]
    return memory_records


def get_chroma_client():
    """
    To use an external Chroma server, set the following environment variables:
        CHROMA_HOST: The host of the Chroma server
        CHROMA_PORT: The port of the Chroma server
        CHROMA_API_KEY: The API key of the Chroma server
        CHROMA_SSL: Set to "true" if the Chroma server uses SSL
    """
    chroma_host = getenv("CHROMA_HOST")
    chroma_settings = Settings(
        anonymized_telemetry=False,
    )
    if chroma_host:
        # Use external Chroma server
        try:
            chroma_api_key = getenv("CHROMA_API_KEY")
            chroma_headers = (
                {"Authorization": f"Bearer {chroma_api_key}"} if chroma_api_key else {}
            )
            return chromadb.HttpClient(
                host=chroma_host,
                port=getenv("CHROMA_PORT"),
                ssl=(False if getenv("CHROMA_SSL").lower() != "true" else True),
                headers=chroma_headers,
                settings=chroma_settings,
            )
        except:
            # If the external Chroma server is not available, use local memories folder
            logging.warning(
                f"Chroma server at {chroma_host} is not available. Using local memories folder."
            )
    # Persist to local memories folder
    memories_dir = os.path.join(os.getcwd(), "memories")
    if not os.path.exists(memories_dir):
        os.makedirs(memories_dir)
    return chromadb.PersistentClient(
        path=memories_dir,
        settings=chroma_settings,
    )


class Memories:
    def __init__(
        self,
        agent_name: str = "AGiXT",
        agent_config=None,
        collection_number: str = "0",  # Is now actually a collection ID and a string to allow conversational memories.
        ApiClient=None,
        summarize_content: bool = False,
        user=DEFAULT_USER,
    ):
        global DEFAULT_USER
        self.agent_name = agent_name
        if not DEFAULT_USER:
            DEFAULT_USER = "user"
        if not user:
            user = "user"
        if user != DEFAULT_USER:
            self.collection_name = f"{snake(user)}_{snake(agent_name)}"
        else:
            self.collection_name = snake(f"{snake(DEFAULT_USER)}_{agent_name}")
        self.user = user
        self.collection_number = collection_number
        # Check if collection_number is a number, it might be a string
        if collection_number != "0":
            self.collection_name = snake(f"{self.collection_name}_{collection_number}")
        if len(collection_number) > 4:
            self.collection_name = snake(f"{collection_number}")
        if agent_config is None:
            agent_config = ApiClient.get_agentconfig(agent_name=agent_name)
        self.agent_config = (
            agent_config
            if agent_config
            else {"settings": {"embeddings_provider": "default"}}
        )
        self.agent_settings = (
            self.agent_config["settings"]
            if "settings" in self.agent_config
            else {"embeddings_provider": "default"}
        )
        self.chroma_client = get_chroma_client()
        self.ApiClient = ApiClient
        self.embedding_provider = Providers(
            name="default",
            ApiClient=ApiClient,
        )
        self.chunk_size = (
            self.embedding_provider.chunk_size
            if hasattr(self.embedding_provider, "chunk_size")
            else 256
        )
        self.embedder = self.embedding_provider.embedder
        self.summarize_content = summarize_content
        self.failures = 0

    async def wipe_memory(self):
        try:
            self.chroma_client.delete_collection(name=self.collection_name)
            return True
        except:
            return False

    async def export_collection_to_json(self):
        collection = await self.get_collection()
        if collection == None:
            return ""
        results = collection.get()
        json_data = []
        for id, document, embedding, metadata in zip(
            results["ids"][0],
            results["documents"][0],
            results["embeddings"][0],
            results["metadatas"][0],
        ):
            json_data.append(
                {
                    "external_source_name": metadata["external_source_name"],
                    "description": metadata["description"],  # User input
                    "text": document,
                    "timestamp": metadata["timestamp"],
                }
            )
        return json_data

    async def export_collections_to_json(self):
        collections = await self.get_collections()
        json_export = []
        for collection in collections:
            self.collection_name = collection
            json_data = await self.export_collection_to_json()
            collection_number = collection.split("_")[-1]
            json_export.append({f"{collection_number}": json_data})
        return json_export

    async def import_collections_from_json(self, json_data: List[dict]):
        for data in json_data:
            for key, value in data.items():
                self.collection_number = key if key else "0"
                self.collection_name = snake(f"{self.user}_{self.agent_name}")
                if str(self.collection_number) != "0":
                    self.collection_name = (
                        f"{self.collection_name}_{self.collection_number}"
                    )
                for val in value[self.collection_name]:
                    try:
                        await self.write_text_to_memory(
                            user_input=val["description"],
                            text=val["text"],
                            external_source=val["external_source_name"],
                        )
                    except:
                        pass

    # get collections that start with the collection name
    async def get_collections(self):
        collections = self.chroma_client.list_collections()
        if str(self.collection_number) != "0":
            collection_name = snake(f"{self.user}_{self.agent_name}")
        else:
            collection_name = self.collection_name
        return [
            collection
            for collection in collections
            if collection.startswith(collection_name)
        ]

    async def get_collection(self):
        try:
            return self.chroma_client.get_or_create_collection(
                name=self.collection_name, embedding_function=self.embedder
            )
        except:
            try:
                return self.chroma_client.create_collection(
                    name=self.collection_name,
                    embedding_function=self.embedder,
                    get_or_create=True,
                )
            except:
                logging.warning(f"Error getting collection: {self.collection_name}")
                return None

    async def delete_memory(self, key: str):
        collection = await self.get_collection()
        try:
            collection.delete(ids=key)
            return True
        except:
            return False

    async def summarize_text(self, text: str) -> str:
        # Chunk size is 1/2 the max tokens of the agent
        try:
            chunk_size = int(self.agent_config["settings"]["MAX_TOKENS"]) / 2
        except:
            chunk_size = 2000
        chunks = await self.chunk_content(text=text, chunk_size=chunk_size)
        summary = ""
        for chunk in chunks:
            # Prompt the agent asking to summarize the information in the chunk.
            response = await self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Summarize Content",
                prompt_args={"user_input": chunk},
            )
            summary += response
        return summary

    async def write_text_to_memory(
        self, user_input: str, text: str, external_source: str = "user input"
    ):
        collection = await self.get_collection()
        if text:
            if not isinstance(text, str):
                text = str(text)
            if self.summarize_content:
                text = await self.summarize_text(text=text)
            chunks = await self.chunk_content(text=text, chunk_size=self.chunk_size)
            for chunk in chunks:
                metadata = {
                    "timestamp": datetime.now().isoformat(),
                    "is_reference": str(False),
                    "external_source_name": external_source,
                    "description": user_input,
                    "additional_metadata": chunk,
                    "id": sha256(
                        (chunk + datetime.now().isoformat()).encode()
                    ).hexdigest(),
                }
                try:
                    collection.add(
                        ids=metadata["id"],
                        metadatas=metadata,
                        documents=chunk,
                    )
                except:
                    self.failures += 1
                    for i in range(5):
                        try:
                            time.sleep(0.1)
                            collection.add(
                                ids=metadata["id"],
                                metadatas=metadata,
                                documents=chunk,
                            )
                            self.failures = 0
                            break
                        except:
                            self.failures += 1
                            if self.failures > 5:
                                break
                            continue
        return True

    async def get_memories_data(
        self,
        user_input: str,
        limit: int,
        min_relevance_score: float = 0.0,
    ) -> List[dict]:
        if not user_input:
            return ""
        collection = await self.get_collection()
        if collection == None:
            return ""
        embedding = array(self.embedding_provider.embeddings(user_input))
        results = collection.query(
            query_embeddings=embedding.tolist(),
            n_results=limit,
            include=["embeddings", "metadatas", "documents"],
        )
        embedding_array = array(results["embeddings"][0])
        if len(embedding_array) == 0:
            return []
        embedding_array = embedding_array.reshape(embedding_array.shape[0], -1)
        if len(embedding.shape) == 2:
            embedding = embedding.reshape(
                embedding.shape[1],
            )
        similarity_score = compute_similarity_scores(
            embedding=embedding, embedding_array=embedding_array
        )
        record_list = []
        for record, score in zip(query_results_to_records(results), similarity_score):
            record["relevance_score"] = score
            record_list.append(record)
        sorted_results = sorted(
            record_list, key=lambda x: x["relevance_score"], reverse=True
        )
        filtered_results = [
            x for x in sorted_results if x["relevance_score"] >= min_relevance_score
        ]
        top_results = filtered_results[:limit]
        return top_results

    async def get_memories(
        self,
        user_input: str,
        limit: int,
        min_relevance_score: float = 0.0,
    ) -> List[str]:
        global DEFAULT_USER
        logging.info(f"Collection name: {self.collection_name}")
        default_collection_name = self.collection_name
        default_results = []
        if self.user != DEFAULT_USER:
            # Get global memories for the agent first
            self.collection_name = snake(f"{snake(DEFAULT_USER)}_{self.agent_name}")
            if str(self.collection_number) != "0":
                self.collection_name = (
                    f"{self.collection_name}_{self.collection_number}"
                )
            if len(self.collection_number) > 4:
                self.collection_name = snake(f"{self.collection_number}")
        try:
            default_results = await self.get_memories_data(
                user_input=user_input,
                limit=limit,
                min_relevance_score=min_relevance_score,
            )
            logging.info(
                f"{len(default_results)} default results found in {self.collection_name}"
            )
        except:
            default_results = []
        self.collection_name = default_collection_name
        if len(self.collection_number) > 4:
            self.collection_name = snake(f"{self.collection_number}")
        logging.info(f"Collection name: {self.collection_name}")
        user_results = await self.get_memories_data(
            user_input=user_input,
            limit=limit,
            min_relevance_score=min_relevance_score,
        )
        logging.info(
            f"{len(user_results)} user results found in {self.collection_name}"
        )
        if isinstance(user_results, str):
            user_results = [user_results]
        if isinstance(default_results, str):
            default_results = [default_results]
        results = user_results + default_results
        response = []
        if results:
            for result in results:
                metadata = (
                    result["additional_metadata"]
                    if "additional_metadata" in result
                    else ""
                )
                external_source = (
                    result["external_source_name"]
                    if "external_source_name" in result
                    else None
                )
                timestamp = (
                    result["timestamp"]
                    if "timestamp" in result
                    else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                if external_source:
                    metadata = f"Sourced from {external_source}:\nSourced on: {timestamp}\n{metadata}"
                if metadata not in response and metadata != "":
                    response.append(metadata)
        return response

    def delete_memories_from_external_source(self, external_source: str):
        collection = self.chroma_client.get_collection(name=self.collection_name)
        if collection:
            results = collection.query(
                query_metadatas={"external_source_name": external_source},
                include=["metadatas"],
            )
            ids = results["metadatas"][0]["id"]
            if ids:
                collection.delete(ids=ids)
                return True
        return False

    def get_external_data_sources(self):
        collection = self.chroma_client.get_collection(name=self.collection_name)
        if collection:
            results = collection.query(
                include=["metadatas"],
            )
            external_sources = results["metadatas"][0]["external_source_name"]
            return list(set(external_sources))
        return []

    def score_chunk(self, chunk: str, keywords: set) -> int:
        """Score a chunk based on the number of query keywords it contains."""
        chunk_counter = Counter(chunk.split())
        score = sum(chunk_counter[keyword] for keyword in keywords)
        return score

    async def chunk_content(self, text: str, chunk_size: int) -> List[str]:
        doc = nlp(text)
        sentences = list(doc.sents)
        content_chunks = []
        chunk = []
        chunk_len = 0
        keywords = set(extract_keywords(doc=doc, limit=10))
        for sentence in sentences:
            sentence_tokens = len(sentence)
            if chunk_len + sentence_tokens > chunk_size and chunk:
                chunk_text = " ".join(token.text for token in chunk)
                content_chunks.append(
                    (self.score_chunk(chunk_text, keywords), chunk_text)
                )
                chunk = []
                chunk_len = 0

            chunk.extend(sentence)
            chunk_len += sentence_tokens

        if chunk:
            chunk_text = " ".join(token.text for token in chunk)
            content_chunks.append((self.score_chunk(chunk_text, keywords), chunk_text))

        # Sort the chunks by their score in descending order before returning them
        content_chunks.sort(key=lambda x: x[0], reverse=True)
        return [chunk_text for score, chunk_text in content_chunks]
