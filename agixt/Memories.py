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


def hash_user_id(user: str, length: int = 8) -> str:
    """
    Creates a consistent, short hash of a user identifier (usually email).

    Args:
        user: User identifier (email)
        length: Desired length of the hash

    Returns:
        str: Short, consistent hash of the user ID
    """
    from hashlib import sha256
    import base64

    # Generate hash of the user identifier
    hash_obj = sha256(user.encode())
    hash_bytes = hash_obj.digest()[:6]  # Take first 6 bytes
    # Use base32 for alphanumeric, url-safe output
    hash_str = base64.b32encode(hash_bytes).decode().lower()

    # Return consistent length hash
    return hash_str[:length]


def normalize_collection_name(
    user: str, agent_name: str, collection_id: str = "0", max_length: int = 63
) -> str:
    """
    Normalizes a collection name with hashed user ID for consistent length.
    Format: uhash_agentname_collectionid

    Args:
        user: User identifier (email)
        agent_name: Name of the agent
        collection_id: Collection identifier/number
        max_length: Maximum length for collection name

    Returns:
        str: Normalized collection name meeting Chroma's requirements
    """
    # Hash the user ID first
    user_hash = hash_user_id(user)

    # Snake case the agent name
    agent_snake = snake(agent_name)

    # Handle conversation IDs (long collection_id)
    if len(collection_id) > 4:
        # For conversation IDs, we'll hash the ID too
        conv_hash = hash_user_id(collection_id, length=10)
        normalized = f"u{user_hash}_{agent_snake}_{conv_hash}"
    else:
        # For normal collections, keep the number
        normalized = f"u{user_hash}_{agent_snake}_{collection_id}"

    # Ensure we're within length limits
    if len(normalized) > max_length:
        # If still too long, truncate agent name but keep user hash and collection id
        available_space = (
            max_length - len(user_hash) - len(collection_id) - 3
        )  # 3 for u_ _
        agent_snake = agent_snake[:available_space]
        normalized = f"u{user_hash}_{agent_snake}_{collection_id}"

    # Ensure it ends with alphanumeric
    while not normalized[-1].isalnum():
        normalized = normalized[:-1]

    # Ensure minimum length of 3
    while len(normalized) < 3:
        normalized += "0"

    return normalized


def get_user_collections_prefix(user: str) -> str:
    """
    Gets the prefix for finding all collections belonging to a user.
    """
    user_hash = hash_user_id(user)
    return f"u{user_hash}_"


def get_base_collection_name(user: str, agent_name: str) -> str:
    """
    Gets the base collection name before normalization.
    This is used to maintain consistent prefix for get_collections().
    """
    return snake(f"{user}_{agent_name}")


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
        self.user = user
        self.collection_name = get_base_collection_name(user, agent_name)
        self.collection_number = collection_number
        # Check if collection_number is a number, it might be a string
        self.collection_name = normalize_collection_name(
            user=self.user,
            agent_name=self.agent_name,
            collection_id=self.collection_number,
        )
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
        prefix = get_user_collections_prefix(self.user)
        # Returns collections that start with the user's prefix
        return [
            collection.name
            for collection in collections
            if collection.name.startswith(prefix)
        ]

    async def get_collection(self):
        try:
            return self.chroma_client.get_or_create_collection(
                name=self.collection_name, embedding_function=self.embedder
            )
        except Exception as e:
            try:
                logging.warning(
                    f"Error275 {e} getting collection: {self.collection_name}"
                )
                return self.chroma_client.create_collection(
                    name=self.collection_name,
                    embedding_function=self.embedder,
                    get_or_create=True,
                )
            except Exception as e:
                logging.warning(
                    f"Error282 {e} getting collection: {self.collection_name}"
                )
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
        # Log the collection number and agent name
        logging.info(f"Saving to collection name: {self.collection_name}")
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
        # If this is a conversation ID, update the collection name
        if len(self.collection_number) > 4:
            self.collection_name = normalize_collection_name(
                user=self.user,
                agent_name=self.agent_name,
                collection_id=self.collection_number,
            )

        logging.info(
            f"Retrieving Memories from collection name: {self.collection_name}"
        )
        results = await self.get_memories_data(
            user_input=user_input,
            limit=limit,
            min_relevance_score=min_relevance_score,
        )
        logging.info(f"{len(results)} user results found in {self.collection_name}")
        if isinstance(results, str):
            results = [results]
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

    async def get_external_data_sources(self):
        """Get a list of all unique external source names from memory collection."""
        collection = await self.get_collection()
        if collection:
            try:
                # Get all documents and their metadata
                results = collection.get()
                if results and "metadatas" in results:
                    # Extract external source names from all metadata entries
                    external_sources = [
                        metadata["external_source_name"]
                        for metadata in results["metadatas"]
                        if "external_source_name" in metadata
                    ]
                    # Return unique sources
                    return list(set(external_sources))
            except Exception as e:
                logging.warning(f"Error getting external sources: {str(e)}")
        return []

    async def delete_memories_from_external_source(self, external_source: str):
        """Delete all memories from a specific external source."""
        collection = await self.get_collection()
        if collection:
            try:
                # Get all documents and their metadata
                results = collection.get()
                if results and "ids" in results and "metadatas" in results:
                    # Find all IDs where external_source_name matches
                    ids_to_delete = [
                        id
                        for id, metadata in zip(results["ids"], results["metadatas"])
                        if metadata.get("external_source_name") == external_source
                    ]
                    if ids_to_delete:
                        collection.delete(ids=ids_to_delete)
                        return True
            except Exception as e:
                logging.warning(
                    f"Error deleting memories from source {external_source}: {str(e)}"
                )
        return False

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
