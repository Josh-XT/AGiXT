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

    async def get_embedder(self):
        try:
            embedder = self.AGENT_CONFIG["settings"]["embedder"]
            embed, chunk_size = await self.__getattribute__(embedder)()
        except:
            embed, chunk_size = await self.default()
            logging.info("Embedder not found, using default embedder")
        return embed, chunk_size

    async def embed_text(self, text):
        embed, chunk_size = await self.get_embedder()
        return await embed(text)

    async def default(self):
        chunk_size = 128
        embed = HuggingFaceTextEmbedding(
            model_id="all-mpnet-base-v2", log=logging
        ).generate_embeddings_async
        return embed, chunk_size

    async def large_local(self):
        chunk_size = 500
        embed = HuggingFaceTextEmbedding(
            model_id="gtr-t5-large", log=logging
        ).generate_embeddings_async
        return embed, chunk_size

    async def azure(self):
        chunk_size = 1000
        embed = AzureTextEmbedding(
            deployment_name=self.AGENT_CONFIG["settings"]["AZURE_DEPLOYMENT_NAME"],
            endpoint=self.AGENT_CONFIG["settings"]["AZURE_OPENAI_ENDPOINT"],
            api_key=self.AGENT_CONFIG["settings"]["AZURE_API_KEY"],
            logger=logging,
        ).generate_embeddings_async
        return embed, chunk_size

    async def openai(self):
        chunk_size = 1000
        if "API_URI" in self.AGENT_CONFIG["settings"]:
            api_base = self.AGENT_CONFIG["settings"]["API_URI"]
        else:
            api_base = None
        embed = OpenAITextEmbedding(
            model_id="text-embedding-ada-002",
            api_key=self.AGENT_CONFIG["settings"]["OPENAI_API_KEY"],
            endpoint=api_base,
            log=logging,
        ).generate_embeddings_async
        return embed, chunk_size

    async def google_palm(self):
        chunk_size = 1000
        embed = embedding_functions.GooglePalmEmbeddingFunction(
            api_key=self.AGENT_CONFIG["settings"]["GOOGLE_API_KEY"],
        )
        return embed, chunk_size

    async def google_vertex(self):
        chunk_size = 1000
        embed = embedding_functions.GoogleVertexEmbeddingFunction(
            api_key=self.AGENT_CONFIG["settings"]["GOOGLE_API_KEY"],
            project_id=self.AGENT_CONFIG["settings"]["GOOGLE_PROJECT_ID"],
        )
        return embed, chunk_size

    async def cohere(self):
        chunk_size = 500
        embed = embedding_functions.CohereEmbeddingFunction(
            api_key=self.AGENT_CONFIG["settings"]["COHERE_API_KEY"],
        )
        return embed, chunk_size

    async def llamacpp(self):
        chunk_size = 250
        embed = LlamacppEmbeddingFunction(
            model_name=self.AGENT_CONFIG["settings"]["EMBEDDING_URI"],
        )
        return embed, chunk_size


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
