import logging
import os
import asyncio
import sys
import json
import spacy
import chromadb
from chromadb.config import Settings
from chromadb.api.types import QueryResult
from numpy import array, linalg, ndarray
from hashlib import sha256
from Embedding import Embedding
from datetime import datetime
from collections import Counter
from typing import List
from Defaults import DEFAULT_USER


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


def snake(old_str: str = ""):
    if old_str == "":
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
            "is_reference": metadata["is_reference"] == "True",
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
    chroma_host = os.environ.get("CHROMA_HOST", None)
    chroma_settings = Settings(
        anonymized_telemetry=False,
    )
    if chroma_host:
        # Use external Chroma server
        try:
            chroma_api_key = os.environ.get("CHROMA_API_KEY", None)
            chroma_headers = (
                {"Authorization": f"Bearer {chroma_api_key}"} if chroma_api_key else {}
            )
            return chromadb.HttpClient(
                host=chroma_host,
                port=os.environ.get("CHROMA_PORT", "8000"),
                ssl=(
                    False
                    if os.environ.get("CHROMA_SSL", "false").lower() != "true"
                    else True
                ),
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
        collection_number: int = 0,
        ApiClient=None,
        summarize_content: bool = False,
        user=DEFAULT_USER,
    ):
        self.agent_name = agent_name
        if user != DEFAULT_USER:
            if user == "":
                user = "USER"
            self.collection_name = f"{snake(user)}_{snake(agent_name)}"
        else:
            self.collection_name = snake(agent_name)
        self.collection_number = collection_number
        if collection_number > 0:
            self.collection_name = f"{self.collection_name}_{collection_number}"
        if agent_config is None:
            agent_config = ApiClient.get_agentconfig(agent_name=agent_name)
        self.agent_config = (
            agent_config if agent_config else {"settings": {"embedder": "default"}}
        )
        self.agent_settings = (
            self.agent_config["settings"]
            if "settings" in self.agent_config
            else {"embedder": "default"}
        )
        self.chroma_client = get_chroma_client()
        self.ApiClient = ApiClient
        self.embed = Embedding(agent_settings=self.agent_settings)
        self.chunk_size = self.embed.chunk_size
        self.embedder = self.embed.embedder
        self.summarize_content = summarize_content

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
                try:
                    collection_number = int(key)
                except:
                    collection_number = 0
                self.collection_number = collection_number
                self.collection_name = snake(self.agent_name)
                if collection_number > 0:
                    self.collection_name = f"{self.collection_name}_{collection_number}"
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
        if int(self.collection_number) > 0:
            collection_name = snake(self.agent_name)
            collection_name = f"{collection_name}_{self.collection_number}"
        else:
            collection_name = self.collection_name
        return [
            collection
            for collection in collections
            if collection.startswith(collection_name)
        ]

    async def get_collection(self):
        try:
            return self.chroma_client.get_collection(
                name=self.collection_name, embedding_function=self.embedder
            )
        except:
            self.chroma_client.create_collection(
                name=self.collection_name,
                embedding_function=self.embedder,
            )
            return self.chroma_client.get_collection(
                name=self.collection_name, embedding_function=self.embedder
            )

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
                collection.add(
                    ids=metadata["id"],
                    metadatas=metadata,
                    documents=chunk,
                )

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
        embedding = array(self.embed.embed_text(text=user_input))
        results = collection.query(
            query_embeddings=embedding.tolist(),
            n_results=limit,
            include=["embeddings", "metadatas", "documents"],
        )
        embedding_array = array(results["embeddings"][0])
        if len(embedding_array) == 0:
            logging.warning("Embedding collection is empty.")
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
        results = await self.get_memories_data(
            user_input=user_input,
            limit=limit,
            min_relevance_score=min_relevance_score,
        )
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
                if external_source:
                    # If the external source is a url or a file path, add it to the metadata
                    if external_source:
                        metadata = f"Sourced from {external_source}:\n{metadata}"
                if metadata not in response and metadata != "":
                    response.append(metadata)
        return response

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
        keywords = [
            token.text for token in doc if token.pos_ in {"NOUN", "PROPN", "VERB"}
        ]
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

    async def get_context(
        self,
        user_input: str,
        limit: int = 10,
        websearch: bool = False,
        additional_collections: List[str] = [],
    ) -> str:
        self.collection_number = 0
        context = await self.get_memories(
            user_input=user_input,
            limit=limit,
            min_relevance_score=0.2,
        )
        self.collection_number = 2
        positive_feedback = await self.get_memories(
            user_input=user_input,
            limit=3,
            min_relevance_score=0.7,
        )
        self.collection_number = 3
        negative_feedback = await self.get_memories(
            user_input=user_input,
            limit=3,
            min_relevance_score=0.7,
        )
        if positive_feedback or negative_feedback:
            context += f"The users input makes you to remember some feedback from previous interactions:\n"
            if positive_feedback:
                context += f"Positive Feedback:\n{positive_feedback}\n"
            if negative_feedback:
                context += f"Negative Feedback:\n{negative_feedback}\n"
        if websearch:
            self.collection_number = 1
            context += await self.get_memories(
                user_input=user_input,
                limit=limit,
                min_relevance_score=0.2,
            )
        if additional_collections:
            for collection in additional_collections:
                self.collection_number = collection
                context += await self.get_memories(
                    user_input=user_input,
                    limit=limit,
                    min_relevance_score=0.2,
                )
        return context

    async def batch_prompt(
        self,
        user_inputs: List[str] = [],
        prompt_name: str = "Ask Questions",
        prompt_category: str = "Default",
        batch_size: int = 10,
        qa: bool = False,
        **kwargs,
    ):
        i = 0
        tasks = []
        responses = []
        if user_inputs == []:
            return []
        for user_input in user_inputs:
            i += 1
            logging.info(f"[{i}/{len(user_inputs)}] Running Prompt: {prompt_name}")
            if i % batch_size == 0:
                responses += await asyncio.gather(**tasks)
                tasks = []
            task = asyncio.create_task(
                await self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name=prompt_name,
                    prompt_args={
                        "prompt_category": prompt_category,
                        "user_input": user_input,
                        **kwargs,
                    },
                )
                if not qa
                else await self.agent_qa(question=user_input, context_results=10)
            )
            tasks.append(task)
        responses += await asyncio.gather(**tasks)
        return responses

    # Answer a question with context injected, return in sharegpt format
    async def agent_qa(self, question: str = "", context_results: int = 10):
        context = await self.get_context(user_input=question, limit=context_results)
        answer = await self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Answer Question with Memory",
            prompt_args={
                "prompt_category": "Default",
                "user_input": question,
                "context_results": context_results,
            },
        )
        # Create a memory with question and answer
        self.collection_number = 0
        await self.write_text_to_memory(
            user_input=question,
            text=answer,
            external_source="Synthetic QA",
        )
        qa = [
            {
                "from": "human",
                "value": f"### Context\n{context}\n### Question\n{question}",
            },
            {"from": "gpt", "value": answer},
        ]
        return qa

    # Creates a synthetic dataset from memories in sharegpt format
    async def create_dataset_from_memories(
        self, dataset_name: str = "", batch_size: int = 10
    ):
        memories = []
        questions = []
        if dataset_name == "":
            dataset_name = f"{datetime.now().isoformat()}-dataset"
        collections = await self.get_collections()
        for collection in collections:
            self.collection_name = collection
            memories += await self.export_collection_to_json()
        logging.info(f"There are {len(memories)} memories.")
        memories = [memory["text"] for memory in memories]
        # Get a list of questions about each memory
        question_list = self.batch_prompt(
            user_inputs=memories,
            qa=False,
            batch_size=batch_size,
        )
        for question in question_list:
            # Convert the response to a list of questions
            question = question.split("\n")
            question = [
                item.lstrip("0123456789.*- ") for item in question if item.lstrip()
            ]
            question = [item for item in question if item]
            question = [item.lstrip("0123456789.*- ") for item in question]
            questions += question
        # Answer each question with context injected
        qa = self.batch_prompt(
            user_inputs=questions,
            qa=True,
            batch_size=batch_size,
        )
        conversations = {"conversations": [qa]}
        # Save messages to a json file to be used as a dataset
        with open(f"{dataset_name}.json", "w") as f:
            f.write(json.dumps(conversations))
        return conversations
