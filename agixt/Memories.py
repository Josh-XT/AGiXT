import os
import pandas as pd
import docx2txt
import pdfplumber
import asyncio
import sys
import chromadb
from chromadb.config import Settings
from chromadb.api.types import QueryResult
from playwright.async_api import async_playwright
from numpy import array, linalg, ndarray
from bs4 import BeautifulSoup
from hashlib import sha256
from Embedding import Embedding, nlp
from datetime import datetime
from collections import Counter
from typing import List
import zipfile
import shutil
import requests

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def camel_to_snake(camel_str):
    camel_str = camel_str.replace(" ", "")
    snake_str = ""
    for i, char in enumerate(camel_str):
        if char.isupper():
            if i != 0 and camel_str[i - 1].islower():
                snake_str += "_"
            if i != len(camel_str) - 1 and camel_str[i + 1].islower():
                snake_str += "_"
        snake_str += char.lower()
    snake_str = snake_str.strip("_")
    return snake_str


def chroma_compute_similarity_scores(
    embedding: ndarray, embedding_array: ndarray, logger=None
) -> ndarray:
    query_norm = linalg.norm(embedding)
    collection_norm = linalg.norm(embedding_array, axis=1)
    valid_indices = (query_norm != 0) & (collection_norm != 0)
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
        self.chroma_client = chromadb.PersistentClient(
            path=memories_dir,
            settings=Settings(
                anonymized_telemetry=False,
            ),
        )
        self.embed = Embedding(AGENT_CONFIG=self.agent_config)
        self.chunk_size = self.embed.chunk_size
        self.embedder = self.embed.embedder

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

    async def store_result(self, input: str, result: str):
        collection = await self.get_collection()
        if result:
            if not isinstance(result, str):
                result = str(result)
            chunks = await self.chunk_content(
                content=result, chunk_size=self.chunk_size
            )
            for chunk in chunks:
                metadata = {
                    "timestamp": datetime.now().isoformat(),
                    "is_reference": str(False),
                    "external_source_name": input,
                    "description": input,
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

    async def get_nearest_matches_async(
        self,
        user_input: str,
        limit: int,
        min_relevance_score: float = 0.0,
    ):
        embedding = array(self.embed.embed_text(text=user_input))
        collection = await self.get_collection()
        if collection is None:
            return []
        query_results = collection.query(
            query_embeddings=embedding.tolist(),
            n_results=limit,
            include=["embeddings", "metadatas", "documents"],
        )
        embedding_array = array(query_results["embeddings"][0])
        embedding_array = embedding_array.reshape(embedding_array.shape[0], -1)
        if len(embedding.shape) == 2:
            embedding = embedding.reshape(
                embedding.shape[1],
            )
        similarity_score = chroma_compute_similarity_scores(embedding, embedding_array)
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

        results = await self.get_nearest_matches_async(
            user_input=user_input,
            limit=limit,
            min_relevance_score=0.0,
        )
        response = "The user's input causes you remember these things:\n"

        for result in results:
            print(result[0]["additional_metadata"])
            metadata = result[0]["additional_metadata"]
            if metadata not in response:
                response += metadata + "\n"

        response += "\n"
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

    async def wipe_memory(self):
        self.chroma_client.delete_collection(name=self.collection_name)

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
            # If zip file, extract it then go over each file with read_file
            elif file_path.endswith(".zip"):
                with zipfile.ZipFile(file_path, "r") as zipObj:
                    zipObj.extractall(path=os.path.join(base_path, "temp"))
                content = ""
                # Iterate over every file that was extracted including subdirectories
                for root, dirs, files in os.walk(os.getcwd()):
                    for name in files:
                        file_path = os.path.join(root, name)
                        await self.read_file(file_path=file_path)
                shutil.rmtree(os.path.join(base_path, "temp"))
            # TODO: If file is an image, classify it in text.
            # Otherwise just read the file
            else:
                with open(file_path, "r") as f:
                    content = f.read()
            if content != "":
                await self.store_result(input=file_path, result=content)
            return True
        except:
            return False

    async def read_website(self, url):
        if "github.com" in url:
            return await self.read_github_repo(github_repo=url)
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url)
            content = await page.content()
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

    async def read_github_repo(
        self, github_repo="Josh-XT/AGiXT", github_user=None, github_token=None
    ):
        github_repo = github_repo.replace("https://github.com/", "")
        github_repo = github_repo.replace("https://www.github.com/", "")
        user = github_repo.split("/")[0]
        repo = github_repo.split("/")[1]
        repo_url = f"https://github.com/{user}/{repo}/archive/refs/heads/main.zip"
        zip_file_name = f"{repo}_main.zip"
        response = requests.get(repo_url, auth=(github_user, github_token))
        with open(zip_file_name, "wb") as f:
            f.write(response.content)
        await self.read_file(file_path=zip_file_name)
