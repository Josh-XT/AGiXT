import os
import pandas as pd
import docx2txt
import pdfplumber
import logging
import asyncio
import sys
import chromadb
from chromadb.config import Settings
from chromadb.api.types import QueryResult
from playwright.async_api import async_playwright
from numpy import array, linalg, ndarray
from bs4 import BeautifulSoup
from hashlib import sha256
from Embedding import Embedding, get_tokens, nlp
from datetime import datetime
from collections import Counter
from typing import List

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def camel_to_snake(camel_str):
    snake_str = ""
    for i, char in enumerate(camel_str):
        if char.isupper():
            if i != 0 and camel_str[i - 1].islower():
                snake_str += "_"
            if i != len(camel_str) - 1 and camel_str[i + 1].islower():
                snake_str += "_"
        snake_str += char.lower()
    return snake_str


def chroma_compute_similarity_scores(
    embedding: ndarray, embedding_array: ndarray, logger=None
) -> ndarray:
    query_norm = linalg.norm(embedding)
    collection_norm = linalg.norm(embedding_array, axis=1)

    # Compute indices for which the similarity scores can be computed
    valid_indices = (query_norm != 0) & (collection_norm != 0)

    # Initialize the similarity scores with -1 to distinguish the cases
    # between zero similarity from orthogonal vectors and invalid similarity
    similarity_scores = array([-1.0] * embedding_array.shape[0])

    if valid_indices.any():
        similarity_scores[valid_indices] = embedding.dot(
            embedding_array[valid_indices].T
        ) / (query_norm * collection_norm[valid_indices])
        if not valid_indices.all() and logger:
            logger.warning(
                "Some vectors in the embedding collection are zero vectors."
                "Ignoring cosine similarity score computation for those vectors."
            )
    else:
        raise ValueError(
            f"Invalid vectors, cannot compute cosine similarity scores"
            f"for zero vectors"
            f"{embedding_array} or {embedding}"
        )
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


class Memories:
    def __init__(self, agent_name: str = "AGiXT", agent_config=None):
        self.agent_name = agent_name
        self.collection_name = camel_to_snake(agent_name)
        self.agent_config = agent_config
        memories_dir = os.path.join(os.getcwd(), "memories")
        if not os.path.exists(memories_dir):
            os.makedirs(memories_dir)
        self.chroma_client = chromadb.Client(
            settings=Settings(
                chroma_db_impl="chromadb.db.duckdb.PersistentDuckDB",
                persist_directory=memories_dir,
                anonymized_telemetry=False,
            )
        )
        self.embedder, self.chunk_size = asyncio.run(
            Embedding(AGENT_CONFIG=self.agent_config).get_embedder()
        )

    async def get_collection(self):
        try:
            # Current version of ChromeDB rejects camel case collection names.
            return self.chroma_client.get_collection(
                name=self.collection_name,
                embedding_function="DisableChromaEmbeddingFunction",
            )
        except:
            self.chroma_client.create_collection(
                name=self.collection_name,
                embedding_function="DisableChromaEmbeddingFunction",
            )
            return self.get_collection()

    async def upsert_async(
        self,
        user_input: str,
        text: str,
    ) -> str:
        collection = await self.get_collection()
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "is_reference": str(False),
            "external_source_name": user_input,
            "description": user_input,
            "additional_metadata": text,
            "id": sha256((text + datetime.now().isoformat()).encode()).hexdigest(),
        }
        embedding = await self.embedder(text)
        collection.add(
            ids=metadata["id"],
            embeddings=embedding.tolist(),
            metadatas=metadata,
            documents=text,
        )
        return metadata["id"]

    async def store_result(self, input: str, result: str):
        if result:
            if not isinstance(result, str):
                result = str(result)
            chunks = await self.chunk_content(
                content=result, chunk_size=self.chunk_size
            )
            for chunk in chunks:
                try:
                    await self.upsert_async(
                        user_input=input,
                        text=chunk,
                    )
                except Exception as e:
                    logging.info(f"Failed to store memory: {e}")
            self.chroma_client.persist()

    async def get_nearest_matches_async(
        self,
        user_input: str,
        limit: int,
        min_relevance_score: float = 0.0,
    ):
        embedding = ndarray(self.embedder(user_input))
        collection = await self.get_collection()
        if collection is None:
            return []

        query_results = collection.query(
            query_embeddings=embedding.tolist(),
            n_results=limit,
            include=["embeddings", "metadatas", "documents"],
        )

        # Convert the collection of embeddings into a numpy array (stacked)
        embedding_array = array(query_results["embeddings"][0])
        embedding_array = embedding_array.reshape(embedding_array.shape[0], -1)

        # If the query embedding has shape (1, embedding_size),
        # reshape it to (embedding_size,)
        if len(embedding.shape) == 2:
            embedding = embedding.reshape(
                embedding.shape[1],
            )

        similarity_score = chroma_compute_similarity_scores(embedding, embedding_array)

        # Convert query results into memory records
        record_list = [
            (record, distance)
            for record, distance in zip(
                query_results_to_records(query_results),
                similarity_score,
            )
        ]

        sorted_results = sorted(
            record_list,
            key=lambda x: x[1],
            reverse=True,
        )

        filtered_results = [x for x in sorted_results if x[1] >= min_relevance_score]
        top_results = filtered_results[:limit]

        return top_results

    async def context_agent(self, user_input: str, limit: int) -> List[str]:
        collection = await self.get_collection()
        if collection == None:
            return []
        try:
            results = await self.get_nearest_matches_async(
                user_input=user_input,
                limit=limit,
                min_relevance_score=0.0,
            )
        except:
            return ""
        context = []
        for memory, score in results:
            context.append(memory._text)
        trimmed_context = []
        total_tokens = 0
        for item in context:
            item_tokens = get_tokens(item)
            if total_tokens + item_tokens <= self.chunk_size:
                trimmed_context.append(item)
                total_tokens += item_tokens
            else:
                break
        logging.info(f"Context Injected: {trimmed_context}")
        context_str = "\n".join(trimmed_context)
        response = (
            f"The user's input causes you remember these things:\n {context_str} \n\n"
        )
        return response

    def score_chunk(self, chunk: str, keywords: set):
        """Score a chunk based on the number of query keywords it contains."""
        chunk_counter = Counter(chunk.split())
        score = sum(chunk_counter[keyword] for keyword in keywords)
        return score

    async def chunk_content(
        self, content: str, chunk_size: int, overlap: int = 2
    ) -> List[str]:
        doc = nlp(content)
        sentences = list(doc.sents)
        content_chunks = []
        chunk = []
        chunk_len = 0
        keywords = [
            token.text for token in doc if token.pos_ in {"NOUN", "PROPN", "VERB"}
        ]

        for i, sentence in enumerate(sentences):
            sentence_tokens = len(sentence)
            if chunk_len + sentence_tokens > chunk_size and chunk:
                chunk_text = " ".join(token.text for token in chunk)
                content_chunks.append(
                    (self.score_chunk(chunk_text, keywords), chunk_text)
                )
                chunk = list(sentences[i - overlap : i]) if i - overlap >= 0 else []
                chunk_len = sum(len(s) for s in chunk)
            chunk.extend(sentence)
            chunk_len += sentence_tokens

        if chunk:
            chunk_text = " ".join(token.text for token in chunk)
            content_chunks.append((self.score_chunk(chunk_text, keywords), chunk_text))

        # Sort the chunks by their score in descending order before returning them
        content_chunks.sort(key=lambda x: x[0], reverse=True)
        return [chunk_text for score, chunk_text in content_chunks]

    async def read_file(self, file_path: str):
        base_path = os.path.join(os.getcwd(), "WORKSPACE")
        file_path = os.path.normpath(os.path.join(base_path, file_path))
        if not file_path.startswith(base_path):
            raise Exception("Path given not allowed")
        try:
            # If file extension is pdf, convert to text
            if file_path.endswith(".pdf"):
                with pdfplumber.open(file_path) as pdf:
                    content = "\n".join([page.extract_text() for page in pdf.pages])
            # If file extension is xls, convert to csv
            elif file_path.endswith(".xls") or file_path.endswith(".xlsx"):
                content = pd.read_excel(file_path).to_csv()
            # If file extension is doc, convert to text
            elif file_path.endswith(".doc") or file_path.endswith(".docx"):
                content = docx2txt.process(file_path)
            # TODO: If file is an image, classify it in text.
            # Otherwise just read the file
            else:
                with open(file_path, "r") as f:
                    content = f.read()
            await self.store_result(input=file_path, result=content)
            return True
        except:
            return False

    async def read_website(self, url):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(url)
                content = await page.content()

                # Scrape links and their titles
                links = await page.query_selector_all("a")
                link_list = []
                for link in links:
                    title = await page.evaluate("(link) => link.textContent", link)
                    href = await page.evaluate("(link) => link.href", link)
                    link_list.append((title, href))

                await browser.close()
                soup = BeautifulSoup(content, "html.parser")
                text_content = soup.get_text()
                text_content = " ".join(text_content.split())
                if text_content:
                    await self.store_result(input=url, result=text_content)
                return text_content, link_list
        except:
            return None, None
