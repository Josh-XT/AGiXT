import chromadb
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
from bs4 import BeautifulSoup


class Memories:
    def __init__(self, agent_name: str = "AGiXT", agent_config=None):
        self.agent_name = agent_name
        self.agent_config = agent_config
        self.chroma_client = None
        self.collection = None
        self.nlp = None
        self.chroma_persist_dir = f"agents/{self.agent_name}/memories"
        if not os.path.exists(self.chroma_persist_dir):
            os.makedirs(self.chroma_persist_dir)

    def load_spacy_model(self):
        if not self.nlp:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except:
                spacy.cli.download("en_core_web_sm")
                self.nlp = spacy.load("en_core_web_sm")
        self.nlp.max_length = 99999999999999999999999

    def initialize_chroma_client(self):
        try:
            return chromadb.Client(
                settings=chromadb.config.Settings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=self.chroma_persist_dir,
                    anonymized_telemetry=False,
                )
            )
        except Exception as e:
            raise RuntimeError(f"Unable to initialize chroma client: {e}")

    def get_or_create_collection(self):
        if not self.chroma_client:
            self.chroma_client = self.initialize_chroma_client()
        embedder = Embedding(self.agent_config)
        self.embedding_function = embedder.embed
        self.chunk_size = embedder.chunk_size
        try:
            return self.chroma_client.get_collection(
                name="memories", embedding_function=self.embedding_function
            )
        except ValueError:
            print(f"Memories for {self.agent_name} do not exist. Creating...")
            return self.chroma_client.create_collection(
                name="memories", embedding_function=self.embedding_function
            )

    def generate_id(self, content: str, timestamp: str):
        return sha256((content + timestamp).encode()).hexdigest()

    def store_memory(self, id: str, content: str, metadatas: dict):
        if not self.chroma_client:
            self.chroma_client = self.initialize_chroma_client()
            self.collection = self.get_or_create_collection()
        try:
            self.collection.add(
                ids=id,
                documents=content,
                metadatas=metadatas,
            )
        except Exception as e:
            print(f"Failed to store memory: {e}")

    def store_result(self, task_name: str, result: str):
        if not self.chroma_client:
            self.chroma_client = self.initialize_chroma_client()
            self.collection = self.get_or_create_collection()
        if result:
            timestamp = datetime.now()  # current time as datetime object
            if not isinstance(result, str):
                result = str(result)
            chunks = self.chunk_content(result, task_name)
            for chunk in chunks:
                result_id = self.generate_id(chunk, timestamp.isoformat())
                self.store_memory(
                    result_id,
                    chunk,
                    {
                        "task": task_name,
                        "result": chunk,
                        "timestamp": timestamp.isoformat(),
                    },
                )

    def context_agent(self, query: str, top_results_num: int) -> List[str]:
        if not self.chroma_client:
            self.chroma_client = self.initialize_chroma_client()
            self.collection = self.get_or_create_collection()
        count = self.collection.count()
        if count == 0:
            return []
        results = self.collection.query(
            query_texts=query,
            n_results=min(top_results_num, count),
            include=["metadatas"],
        )
        sorted_results = sorted(
            results["metadatas"][0],
            key=lambda item: datetime.strptime(
                item.get("timestamp") or "1970-01-01T00:00:00.000",
                "%Y-%m-%dT%H:%M:%S.%f",
            ),
            reverse=True,
        )
        # TODO: Before sending results, ask AI if each chunk it is relevant to the task-
        #   so that we're only injecting relevant memories into the context.
        # This will ensure we aren't injecting memories that aren't relevant.
        # Need to research to find out how to do this locally instead of sending more shots to the AI.
        context = [item["result"] for item in sorted_results]
        trimmed_context = self.trim_context(context)
        print(f"CONTEXT: {trimmed_context}")
        context_str = "\n".join(trimmed_context)
        response = f"Context: {context_str}\n\n"
        return response

    def trim_context(self, context: List[str]) -> List[str]:
        if not self.nlp:
            self.load_spacy_model()
        trimmed_context = []
        total_tokens = 0
        for item in context:
            item_tokens = len(self.nlp(item))
            if total_tokens + item_tokens <= self.chunk_size:
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

    def chunk_content(self, content: str, query: str, overlap: int = 2) -> List[str]:
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
            if chunk_len + sentence_tokens > self.chunk_size and chunk:
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

    def read_file(self, file_path: str):
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
            self.store_result(task_name=file_path, result=content)
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
                    self.store_result(url, text_content)
                return text_content, link_list
        except:
            return None, None
