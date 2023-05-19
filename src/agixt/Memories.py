import chromadb
from typing import List
import spacy
from hashlib import sha256
from Embedding import Embedding
from datetime import datetime
from collections import Counter


class Memories:
    def __init__(self, AGENT_NAME: str = "XTAgent", AgentConfig=None, nlp=None):
        self.AGENT_NAME = AGENT_NAME
        self.CFG = AgentConfig
        self.nlp = nlp if nlp else self.load_spacy_model()
        self.nlp.max_length = 999999999999999999999999999999999
        embedder = Embedding(CFG=AgentConfig)
        self.embedding_function = embedder.embed
        self.chunk_size = embedder.chunk_size
        self.chroma_persist_dir = f"agents/{self.AGENT_NAME}/memories"
        self.chroma_client = self.initialize_chroma_client()
        self.collection = self.get_or_create_collection()

    def load_spacy_model(self):
        try:
            return spacy.load("en_core_web_sm")
        except:
            spacy.cli.download("en_core_web_sm")
            return spacy.load("en_core_web_sm")

    def initialize_chroma_client(self):
        try:
            return chromadb.Client(
                settings=chromadb.config.Settings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=self.chroma_persist_dir,
                )
            )
        except Exception as e:
            raise RuntimeError(f"Unable to initialize chroma client: {e}")

    def get_or_create_collection(self):
        try:
            return self.chroma_client.get_collection(
                name="memories", embedding_function=self.embedding_function
            )
        except ValueError:
            print(f"Memories for {self.AGENT_NAME} do not exist. Creating...")
            return self.chroma_client.create_collection(
                name="memories", embedding_function=self.embedding_function
            )

    def generate_id(self, content: str, timestamp: str):
        return sha256((content + timestamp).encode()).hexdigest()

    def store_memory(self, id: str, content: str, metadatas: dict):
        try:
            self.collection.add(
                ids=id,
                documents=content,
                metadatas=metadatas,
            )
        except Exception as e:
            print(f"Failed to store memory: {e}")

    def store_result(self, task_name: str, result: str):
        if result:
            timestamp = datetime.now()  # current time as datetime object
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
        count = self.collection.count()
        if count == 0:
            return []
        results = self.collection.query(
            query_texts=query,
            n_results=min(top_results_num, count),
            include=["metadatas"],
        )
        # Parse timestamps and sort the results by timestamp in descending order
        sorted_results = sorted(
            results["metadatas"][0],
            key=lambda item: datetime.strptime(
                item.get("timestamp") or "1970-01-01T00:00:00.000",
                "%Y-%m-%dT%H:%M:%S.%f",
            ),
            reverse=True,
        )

        context = [item["result"] for item in sorted_results]
        trimmed_context = self.trim_context(context)
        print(f"CONTEXT: {trimmed_context}")
        return "\n".join(trimmed_context)

    def trim_context(self, context: List[str]) -> List[str]:
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
        content_chunks = []
        doc = self.nlp(content)
        sentences = list(doc.sents)
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
