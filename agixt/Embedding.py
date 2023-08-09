import requests
import inspect
from chromadb.utils import embedding_functions
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from semantic_kernel.connectors.ai.hugging_face import HuggingFaceTextEmbedding
from semantic_kernel.connectors.ai.open_ai import (
    AzureTextEmbedding,
    OpenAITextEmbedding,
)
import logging
import spacy


class LlamacppEmbeddingFunction(EmbeddingFunction):
    def __init__(self, api_host: str):
        self._api_host = api_host
        self._session = requests.Session()

    def __call__(self, texts: Documents) -> Embeddings:
        response = self._session.post(
            self._api_url, json={"content": texts, "threads": 5}
        ).json()
        if "data" in response:
            if "embedding" in response["data"]:
                return response["data"]["embedding"]
        return {}


class Embedding:
    def __init__(self, AGENT_CONFIG=None):
        self.AGENT_CONFIG = AGENT_CONFIG

    def get_embedder(self):
        embedder = self.AGENT_CONFIG["settings"]["EMBEDDING_FUNCTION"]
        if embedder == "default":
            chunk_size = 128
            embed = self.default()
        elif embedder == "large_local":
            chunk_size = 500
            embed = self.large_local()
        elif embedder == "azure":
            chunk_size = 1000
            embed = self.azure()
        elif embedder == "openai":
            chunk_size = 1000
            embed = self.openai()
        elif embedder == "google_palm":
            chunk_size = 1000
            embed = self.google_palm()
        elif embedder == "google_vertex":
            chunk_size = 1000
            embed = self.google_vertex()
        elif embedder == "cohere":
            chunk_size = 500
            embed = self.cohere()
        elif embedder == "llamacpp":
            chunk_size = 250
            embed = self.llamacpp()
        else:
            raise Exception("Embedding function not found")
        return embed, chunk_size

    async def embed_text(self, text):
        embed, chunk_size = self.get_embedder()
        return await embed(text)

    async def default(self):
        embed = HuggingFaceTextEmbedding(
            model_id="all-mpnet-base-v2", log=logging
        ).generate_embeddings_async
        return embed

    async def large_local(self):
        embed = HuggingFaceTextEmbedding(
            model_id="gtr-t5-large", log=logging
        ).generate_embeddings_async
        return embed

    async def azure(self):
        embed = AzureTextEmbedding(
            deployment_name=self.AGENT_CONFIG["settings"]["AZURE_DEPLOYMENT_NAME"],
            endpoint=self.AGENT_CONFIG["settings"]["AZURE_OPENAI_ENDPOINT"],
            api_key=self.AGENT_CONFIG["settings"]["AZURE_API_KEY"],
            logger=logging,
        ).generate_embeddings_async
        return embed

    async def openai(self):
        if "API_URI" in self.AGENT_CONFIG["settings"]:
            if self.AGENT_CONFIG["settings"]["API_URI"] != "":
                api_base = self.AGENT_CONFIG["settings"]["API_URI"]
            else:
                api_base = None
        else:
            api_base = None
        embed = OpenAITextEmbedding(
            model_id="text-embedding-ada-002",
            api_key=self.AGENT_CONFIG["settings"]["OPENAI_API_KEY"],
            endpoint=api_base,
            log=logging,
        ).generate_embeddings_async
        return embed

    async def google_palm(self):
        embed = embedding_functions.GooglePalmEmbeddingFunction(
            api_key=self.AGENT_CONFIG["settings"]["GOOGLE_API_KEY"],
        )
        return embed

    async def google_vertex(self):
        embed = embedding_functions.GoogleVertexEmbeddingFunction(
            api_key=self.AGENT_CONFIG["settings"]["GOOGLE_API_KEY"],
            project_id=self.AGENT_CONFIG["settings"]["GOOGLE_PROJECT_ID"],
        )
        return embed

    async def cohere(self):
        embed = embedding_functions.CohereEmbeddingFunction(
            api_key=self.AGENT_CONFIG["settings"]["COHERE_API_KEY"],
        )
        return embed

    async def llamacpp(self):
        embed = LlamacppEmbeddingFunction(
            model_name=self.AGENT_CONFIG["settings"]["EMBEDDING_URI"],
        )
        return embed


def get_embedding_providers():
    return [
        func
        for func, _ in inspect.getmembers(Embedding, predicate=inspect.isfunction)
        if not func.startswith("__")
    ]


def nlp(text):
    try:
        sp = spacy.load("en_core_web_sm")
    except:
        spacy.cli.download("en_core_web_sm")
        sp = spacy.load("en_core_web_sm")
    sp.max_length = 99999999999999999999999
    return sp(text)


def get_tokens(text):
    return len(nlp(text))
