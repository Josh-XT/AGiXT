from typing import List
import spacy
import os
from hashlib import sha256
from Embedding import Embedding
from datetime import datetime
from collections import Counter
import pandas as pd
import docx2txt
import pdfplumber
from playwright.async_api import async_playwright
from semantic_kernel.connectors.memory.chroma import ChromaMemoryStore
from semantic_kernel.memory.memory_record import MemoryRecord
from chromadb.config import Settings
from bs4 import BeautifulSoup
import logging
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class Memories:
    def __init__(self, agent_name: str = "AGiXT", agent_config=None):
        self.agent_name = agent_name
        self.agent_config = agent_config
        self.chroma_client = None
        self.collection = None
        self.nlp = None
        self.chunk_size = 128
        memories_dir = os.path.join(os.getcwd(), "agents", self.agent_name, "memories")
        self.chroma_client = ChromaMemoryStore(
            persist_directory=memories_dir,
            client_settings=Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=memories_dir,
                anonymized_telemetry=False,
            ),
        )

    def load_spacy_model(self):
        if not self.nlp:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except:
                spacy.cli.download("en_core_web_sm")
                self.nlp = spacy.load("en_core_web_sm")
        self.nlp.max_length = 99999999999999999999999

    async def get_embedder(self):
        embedder, chunk_size = await Embedding(
            AGENT_CONFIG=self.agent_config
        ).get_embedder()
        return embedder, chunk_size

    async def get_collection(self):
        try:
            memories_exist = await self.chroma_client.does_collection_exist_async(
                "memories"
            )
            if not memories_exist:
                await self.chroma_client.create_collection_async(
                    collection_name="memories"
                )
                memories = await self.chroma_client.get_collection_async(
                    collection_name="memories"
                )
            else:
                memories = await self.chroma_client.get_collection_async(
                    collection_name="memories"
                )
            return memories
        except Exception as e:
            raise RuntimeError(f"Unable to initialize chroma client: {e}")

    async def store_memory(
        self, content: str, description: str = None, external_source_name: str = None
    ):
        embedder, chunk_size = await self.get_embedder()
        collection = await self.get_collection()
        record = MemoryRecord(
            is_reference=False,
            id=sha256((content + datetime.now().isoformat()).encode()).hexdigest(),
            text=content,
            timestamp=datetime.now().isoformat(),
            description=description,
            external_source_name=external_source_name,  # URL or File path
            embedding=await embedder(content),
        )

        try:
            await self.chroma_client.upsert_async(
                collection_name="memories",
                record=record,
            )
            self.chroma_client._client.persist()
        except Exception as e:
            logging.info(f"Failed to store memory: {e}")

    async def store_result(
        self, task_name: str, result: str, external_source_name: str = None
    ):
        if result:
            if not isinstance(result, str):
                result = str(result)
            chunks = await self.chunk_content(result, task_name)
            for chunk in chunks:
                await self.store_memory(
                    content=chunk,
                    description=task_name,
                    external_source_name=external_source_name,
                )

    async def context_agent(self, query: str, top_results_num: int) -> List[str]:
        embedder, chunk_size = await self.get_embedder()
        collection = await self.get_collection()
        if collection == None:
            return []
        results = await self.chroma_client.get_nearest_matches_async(
            collection_name="memories",
            embedding=await embedder(query),
            limit=top_results_num,
            min_relevance_score=0.1,
        )
        context = []
        for memory, score in results:
            context.append(memory._text)
        trimmed_context = await self.trim_context(context)
        logging.info(f"CONTEXT: {trimmed_context}")
        context_str = "\n".join(trimmed_context)
        response = f"Context: {context_str}\n\n"
        return response

    async def trim_context(self, context: List[str]) -> List[str]:
        embedder, chunk_size = await self.get_embedder()
        if not self.nlp:
            self.load_spacy_model()
        trimmed_context = []
        total_tokens = 0
        for item in context:
            item_tokens = len(self.nlp(item))
            if total_tokens + item_tokens <= chunk_size:
                trimmed_context.append(item)
                total_tokens += item_tokens
            else:
                break
        return trimmed_context

    def get_keywords(self, query: str):
        """Extract keywords from a query using Spacy's part-of-speech tagging."""
        if not self.nlp:
            self.load_spacy_model()
        doc = self.nlp(query)
        keywords = [
            token.text for token in doc if token.pos_ in {"NOUN", "PROPN", "VERB"}
        ]
        return set(keywords)

    def score_chunk(self, chunk: str, keywords: set):
        """Score a chunk based on the number of query keywords it contains."""
        chunk_counter = Counter(chunk.split())
        score = sum(chunk_counter[keyword] for keyword in keywords)
        return score

    async def chunk_content(
        self, content: str, query: str, overlap: int = 2
    ) -> List[str]:
        embedder, chunk_size = await self.get_embedder()
        if not self.nlp:
            self.load_spacy_model()
        doc = self.nlp(content)
        sentences = list(doc.sents)
        content_chunks = []
        chunk = []
        chunk_len = 0
        keywords = self.get_keywords(query)

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

    async def mem_read_file(self, file_path: str):
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
            await self.store_result(task_name=file_path, result=content)
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
                    await self.store_result(url, text_content)
                return text_content, link_list
        except:
            return None, None
