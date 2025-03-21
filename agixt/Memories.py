import logging
import os
import asyncio
import sys
from DB import (
    Memory,
    Agent,
    User,
    get_session,
    get_similar_memories,
    process_embedding_for_storage,
)
import spacy
from numpy import array, linalg, ndarray
from collections import Counter
from typing import List
from Globals import getenv, DEFAULT_USER
from textacy.extract.keyterms import textrank  # type: ignore
from youtube_transcript_api import YouTubeTranscriptApi
from onnxruntime import InferenceSession
from tokenizers import Tokenizer
from typing import List, cast, Union, Sequence
from numpy import array, linalg, ndarray
import numpy as np
from datetime import datetime
from uuid import UUID

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


def embed(input: List[str]) -> List[Union[Sequence[float], Sequence[int]]]:
    tokenizer = Tokenizer.from_file(os.path.join(os.getcwd(), "onnx", "tokenizer.json"))
    tokenizer.enable_truncation(max_length=256)
    tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=256)
    model = InferenceSession(os.path.join(os.getcwd(), "onnx", "model.onnx"))
    all_embeddings = []
    for i in range(0, len(input), 32):
        batch = input[i : i + 32]
        encoded = [tokenizer.encode(d) for d in batch]
        input_ids = np.array([e.ids for e in encoded])
        attention_mask = np.array([e.attention_mask for e in encoded])
        onnx_input = {
            "input_ids": np.array(input_ids, dtype=np.int64),
            "attention_mask": np.array(attention_mask, dtype=np.int64),
            "token_type_ids": np.array(
                [np.zeros(len(e), dtype=np.int64) for e in input_ids],
                dtype=np.int64,
            ),
        }
        model_output = model.run(None, onnx_input)
        last_hidden_state = model_output[0]
        input_mask_expanded = np.broadcast_to(
            np.expand_dims(attention_mask, -1), last_hidden_state.shape
        )
        embeddings = np.sum(last_hidden_state * input_mask_expanded, 1) / np.clip(
            input_mask_expanded.sum(1), a_min=1e-9, a_max=None
        )
        norm = np.linalg.norm(embeddings, axis=1)
        norm[norm == 0] = 1e-12
        embeddings = (embeddings / norm[:, np.newaxis]).astype(np.float32)
        all_embeddings.append(embeddings)
    return cast(
        List[Union[Sequence[float], Sequence[int]]], np.concatenate(all_embeddings)
    ).tolist()


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


def query_results_to_records(results):
    try:
        if isinstance(results["ids"][0], str):
            for k, v in results.items():
                results[k] = [v]
    except IndexError:
        return []
    memory_records = []
    for id, document, embedding, metadata in zip(
        results["ids"][0],
        results["documents"][0],
        results["embeddings"][0],
        results["metadatas"][0],
    ):
        if metadata:
            memory_records.append(
                {
                    "external_source_name": metadata.get(
                        "external_source_name", "user input"
                    ),
                    "id": metadata["id"],
                    "description": metadata["description"],
                    "text": document,
                    "embedding": embedding,
                    "additional_metadata": metadata["additional_metadata"],
                    "key": id,
                    "timestamp": metadata["timestamp"],
                }
            )
    return memory_records


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


def get_agent_id(agent_name: str, email: str) -> str:
    """
    Gets the agent ID for the given agent name and user.
    """
    session = get_session()
    try:
        user = session.query(User).filter_by(email=email).first()
        agent = session.query(Agent).filter_by(name=agent_name, user_id=user.id).first()
        if agent:
            return str(agent.id)
        else:
            agent = session.query(Agent).filter_by(user_id=user.id).first()
            if agent:
                return str(agent.id)
            else:
                return None
    finally:
        session.close()


class SQLCollection:
    def __init__(self, session, memories_instance):
        self.session = session
        self.memories = memories_instance

    def query(self, query_embeddings, n_results=None, include=None):
        """Emulate ChromaDB's query method using unified vector search"""
        try:
            if isinstance(query_embeddings, np.ndarray):
                query_embeddings = query_embeddings.tolist()

            memory_results = get_similar_memories(
                self.session,
                query_embeddings[0],  # Assuming single query
                self.memories.agent_id,
                (
                    None
                    if self.memories.collection_number == "0"
                    else self.memories.collection_number
                ),
                n_results or 10,
                0.0,  # No minimum score for ChromaDB-style queries
            )

            if not memory_results:
                return {
                    "ids": [[]],
                    "documents": [[]],
                    "embeddings": [[]],
                    "metadatas": [[]],
                }

            # Format results to match ChromaDB's expected structure
            formatted_results = {
                "ids": [[str(mem.id) for mem, _ in memory_results]],
                "documents": [[mem.text for mem, _ in memory_results]],
                "embeddings": [[mem.embedding for mem, _ in memory_results]],
                "metadatas": [
                    [
                        {
                            "external_source_name": mem.external_source,
                            "id": str(mem.id),
                            "description": mem.description,
                            "additional_metadata": mem.additional_metadata,
                            "timestamp": format_timestamp_iso(mem.timestamp),
                            "distance": 1 - sim,  # Convert similarity to distance
                        }
                        for mem, sim in memory_results
                    ]
                ],
            }

            return formatted_results

        except Exception as e:
            logging.error(f"Error in query: {e}")
            return {
                "ids": [[]],
                "documents": [[]],
                "embeddings": [[]],
                "metadatas": [[]],
            }

    def get(self):
        # Existing get method remains the same...
        memories = (
            self.session.query(Memory)
            .filter_by(
                agent_id=self.memories.agent_id,
                conversation_id=(
                    None
                    if self.memories.collection_number == "0"
                    else self.memories.collection_number
                ),
            )
            .all()
        )

        if not memories:
            return {
                "ids": [[]],
                "documents": [[]],
                "embeddings": [[]],
                "metadatas": [[]],
            }

        return {
            "ids": [[m.id for m in memories]],
            "documents": [[m.text for m in memories]],
            "embeddings": [[m.embedding for m in memories]],
            "metadatas": [
                [
                    {
                        "external_source_name": m.external_source,
                        "id": m.id,
                        "description": m.description,
                        "additional_metadata": m.additional_metadata,
                        "timestamp": m.timestamp.isoformat(),
                    }
                    for m in memories
                ]
            ],
        }

    def delete(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        try:
            self.session.query(Memory).filter(Memory.id.in_(ids)).delete(
                synchronize_session="fetch"
            )
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            logging.error(f"Error deleting memories: {e}")
            return False

    def add(self, ids, metadatas, documents):
        try:
            for id, metadata, document in zip(ids, metadatas, documents):
                embedding = embed([document])
                memory = Memory(
                    id=id,
                    agent_id=self.memories.agent_id,
                    conversation_id=(
                        None
                        if self.memories.collection_number == "0"
                        else self.memories.collection_number
                    ),
                    embedding=embedding,
                    text=document,
                    external_source=metadata.get("external_source_name", "user input"),
                    description=metadata.get("description", ""),
                    additional_metadata=metadata.get("additional_metadata", ""),
                )
                self.session.add(memory)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            logging.error(f"Error adding memories: {e}")
            return False


def format_timestamp_iso(timestamp):
    """Helper function to handle different timestamp formats and return ISO format"""
    if isinstance(timestamp, datetime):
        return timestamp.isoformat()
    elif isinstance(timestamp, str):
        return timestamp
    else:
        return datetime.now().isoformat()


def format_timestamp(timestamp):
    """Helper function to handle different timestamp formats"""
    if isinstance(timestamp, datetime):
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(timestamp, str):
        return timestamp
    else:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
        self.agent_id = get_agent_id(agent_name=agent_name, email=self.user)
        self.collection_name = get_base_collection_name(user, agent_name)
        try:
            self.collection_number = str(UUID(collection_number))
        except:
            self.collection_number = "0"
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
        self.ApiClient = ApiClient
        self.chunk_size = 256
        self.summarize_content = summarize_content
        self.failures = 0

    async def wipe_memory(self, conversation_id: str = None):
        session = get_session()
        try:
            query = session.query(Memory).filter_by(agent_id=self.agent_id)
            if conversation_id:
                query = query.filter_by(conversation_id=conversation_id)
            query.delete()
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logging.error(f"Error wiping memory: {e}")
            return False
        finally:
            session.close()

    async def export_collection_to_json(self):
        session = get_session()
        try:
            memories = (
                session.query(Memory)
                .filter_by(
                    agent_id=self.agent_id,
                    conversation_id=(
                        self.collection_number
                        if self.collection_number != "0"
                        else None
                    ),
                )
                .all()
            )

            json_data = []
            for memory in memories:
                json_data.append(
                    {
                        "external_source_name": memory.external_source,
                        "description": memory.description,
                        "text": memory.text,
                        "timestamp": memory.timestamp.isoformat(),
                    }
                )
            return json_data
        finally:
            session.close()

    async def export_collections_to_json(self):
        session = get_session()
        try:
            memories = session.query(Memory).filter_by(agent_id=self.agent_id).all()

            # Group by conversation_id
            memory_by_conversation = {}
            for memory in memories:
                conv_id = memory.conversation_id or "0"
                if conv_id not in memory_by_conversation:
                    memory_by_conversation[conv_id] = []
                memory_by_conversation[conv_id].append(
                    {
                        "external_source_name": memory.external_source,
                        "description": memory.description,
                        "text": memory.text,
                        "timestamp": memory.timestamp.isoformat(),
                    }
                )

            return [
                {conversation_id: memories}
                for conversation_id, memories in memory_by_conversation.items()
            ]
        finally:
            session.close()

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
    async def get_collection(self):
        """Emulate ChromaDB collection interface using SQL"""
        session = get_session()
        try:
            return SQLCollection(session, self)
        except Exception as e:
            logging.warning(f"Error getting collection: {e}")
            return None

    async def get_collections(self):
        """Emulate ChromaDB collections listing using SQL"""
        session = get_session()
        try:
            # Get distinct conversation IDs for this agent
            conversations = (
                session.query(Memory.conversation_id)
                .filter_by(agent_id=self.agent_id)
                .distinct()
                .all()
            )

            # Format collection names like ChromaDB expected them
            prefix = get_user_collections_prefix(self.user)
            collections = []

            # Add collection "0" if it exists (core memories)
            if (
                session.query(Memory)
                .filter_by(agent_id=self.agent_id, conversation_id=None)
                .first()
            ):
                collections.append(f"{prefix}{snake(self.agent_name)}_0")

            # Add conversation-specific collections
            for (conv_id,) in conversations:
                if conv_id:  # Skip None which represents collection "0"
                    conv_hash = hash_user_id(conv_id, length=10)
                    collections.append(f"{prefix}{snake(self.agent_name)}_{conv_hash}")

            return collections
        finally:
            session.close()

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
        """Write text to memory with proper validation"""
        if not self.agent_id:
            logging.error(
                f"No agent_id found for agent {self.agent_name} and user {self.user}"
            )
            return False

        session = get_session()
        try:
            # Validate agent exists
            agent = session.query(Agent).filter_by(id=self.agent_id).first()
            if not agent:
                logging.error(f"Agent not found with id {self.agent_id}")
                return False

            chunks = await self.chunk_content(text=text, chunk_size=self.chunk_size)

            # Handle core memories vs conversation memories
            conversation_id = (
                None if self.collection_number == "0" else self.collection_number
            )

            # If replacing external source content, delete old entries
            if external_source.startswith(("file", "http://", "https://")):
                session.query(Memory).filter_by(
                    agent_id=self.agent_id,
                    conversation_id=conversation_id,
                    external_source=external_source,
                ).delete()

            # Process all chunks first to ensure they're valid
            memories_to_add = []
            for chunk in chunks:
                # Get embedding and ensure proper shape
                try:
                    chunk_embedding = embed([chunk])
                    if not chunk_embedding or len(chunk_embedding) == 0:
                        logging.warning(
                            f"Failed to generate embedding for chunk: {chunk[:100]}..."
                        )
                        continue

                    embedding = process_embedding_for_storage(chunk_embedding[0])

                    memory = Memory(
                        agent_id=self.agent_id,  # Explicitly set agent_id
                        conversation_id=conversation_id,
                        embedding=embedding,
                        text=chunk,
                        external_source=external_source,
                        description=user_input,
                        additional_metadata=chunk,
                    )
                    # Validate memory object
                    if not memory.agent_id:
                        logging.error("Memory created with null agent_id")
                        continue

                    memories_to_add.append(memory)
                except Exception as e:
                    logging.error(f"Error processing chunk: {str(e)}")
                    continue

            # Add all valid memories
            if memories_to_add:
                session.bulk_save_objects(memories_to_add)
                session.commit()
                logging.info(f"Successfully added {len(memories_to_add)} memories")
                return True
            else:
                logging.warning("No valid memories to add")
                return False

        except Exception as e:
            session.rollback()
            logging.error(f"Error writing to memory: {e}")
            return False
        finally:
            session.close()

    # Update the get_memories_data method:
    async def get_memories_data(
        self,
        user_input: str,
        limit: int,
        min_relevance_score: float = 0.0,
    ) -> List[dict]:
        if not user_input:
            return []

        session = get_session()
        try:
            query_embedding = embed([user_input])[0]
            conversation_id = (
                None if self.collection_number == "0" else self.collection_number
            )

            # Get similar memories using the new helper function
            memory_results = get_similar_memories(
                session,
                query_embedding,
                self.agent_id,
                conversation_id,
                limit,
                min_relevance_score,
            )

            # Format results
            memories = []
            for memory, similarity in memory_results:
                memories.append(
                    {
                        "external_source_name": memory.external_source,
                        "id": str(memory.id),
                        "key": str(memory.id),
                        "description": memory.description,
                        "text": memory.text,
                        "embedding": (
                            memory.embedding.tolist()
                            if isinstance(memory.embedding, np.ndarray)
                            else memory.embedding
                        ),
                        "additional_metadata": memory.additional_metadata,
                        "timestamp": format_timestamp_iso(memory.timestamp),
                        "relevance_score": float(similarity),
                    }
                )

            return memories

        finally:
            session.close()

    # Update the get_memories method similarly:
    async def get_memories(
        self,
        user_input: str,
        limit: int,
        min_relevance_score: float = 0.0,
    ) -> List[str]:
        session = get_session()
        try:
            query_embedding = embed([user_input])[0]
            conversation_id = (
                None if self.collection_number == "0" else self.collection_number
            )

            # Get similar memories using the new helper function
            memory_results = get_similar_memories(
                session,
                query_embedding,
                self.agent_id,
                conversation_id,
                limit,
                min_relevance_score,
            )

            # Format results
            response = []
            for memory, similarity in memory_results:
                metadata = (
                    memory.additional_metadata if memory.additional_metadata else ""
                )
                external_source = (
                    memory.external_source if memory.external_source else None
                )
                timestamp = format_timestamp(memory.timestamp)

                if external_source:
                    metadata = f"Sourced from {external_source}:\nSourced on: {timestamp}\n{metadata}"

                if metadata not in response and metadata != "":
                    response.append(metadata)

            return response

        finally:
            session.close()

    async def get_external_data_sources(self):
        session = get_session()
        try:
            sources = (
                session.query(Memory.external_source)
                .filter_by(agent_id=self.agent_id)
                .distinct()
                .all()
            )
            return [source[0] for source in sources if source[0]]
        finally:
            session.close()

    async def delete_memories_from_external_source(self, external_source: str):
        session = get_session()
        try:
            if external_source.startswith("file"):
                file_path = external_source.split(" ")[1]
                file_path = os.path.normpath(file_path)
                working_directory = os.path.normpath(getenv("WORKING_DIRECTORY"))
                if file_path.startswith(working_directory):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logging.error(f"Error deleting file: {str(e)}")

            result = (
                session.query(Memory)
                .filter_by(agent_id=self.agent_id, external_source=external_source)
                .delete()
            )

            session.commit()
            return bool(result)
        except Exception as e:
            session.rollback()
            logging.error(f"Error deleting memories: {str(e)}")
            return False
        finally:
            session.close()

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

    async def get_transcription(self, video_id: str = None):
        if "?v=" in video_id:
            video_id = video_id.split("?v=")[1]
        srt = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US"])
        content = ""
        for line in srt:
            if line["text"] != "[Music]":
                content += line["text"].replace("[Music]", "") + " "
        return content

    async def write_youtube_captions_to_memory(self, video_id: str = None):
        content = await self.get_transcription(video_id=video_id)
        if content != "":
            stored_content = (
                f"Content from video at youtube.com/watch?v={video_id}:\n{content}"
            )
            await self.write_text_to_memory(
                user_input=video_id,
                text=stored_content,
                external_source=f"From YouTube video: {video_id}",
            )
            return True
        return False
