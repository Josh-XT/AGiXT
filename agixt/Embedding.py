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


class GooglePalmEmbeddingFunction(EmbeddingFunction):
    """To use this EmbeddingFunction, you must have the google.generativeai Python package installed and have a PaLM API key."""

    def __init__(self, api_key: str, model_name: str = "models/embedding-gecko-001"):
        if not api_key:
            raise ValueError("Please provide a PaLM API key.")

        if not model_name:
            raise ValueError("Please provide the model name.")

        try:
            import google.generativeai as palm
        except ImportError:
            raise ValueError(
                "The Google Generative AI python package is not installed. Please install it with `pip install google-generativeai`"
            )

        palm.configure(api_key=api_key)
        self._palm = palm
        self._model_name = model_name

    def __call__(self, texts: Documents) -> Embeddings:
        return [
            self._palm.generate_embeddings(model=self._model_name, text=text)[
                "embedding"
            ]
            for text in texts
        ]


class GoogleVertexEmbeddingFunction(EmbeddingFunction):
    # Follow API Quickstart for Google Vertex AI
    # https://cloud.google.com/vertex-ai/docs/generative-ai/start/quickstarts/api-quickstart
    # Information about the text embedding modules in Google Vertex AI
    # https://cloud.google.com/vertex-ai/docs/generative-ai/embeddings/get-text-embeddings
    def __init__(
        self,
        api_key: str,
        model_name: str = "textembedding-gecko-001",
        project_id: str = "cloud-large-language-models",
        region: str = "us-central1",
    ):
        self._api_url = f"https://{region}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{region}/endpoints/{model_name}:predict"
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {api_key}"})

    def __call__(self, texts: Documents) -> Embeddings:
        response = self._session.post(
            self._api_url, json={"instances": [{"content": texts}]}
        ).json()

        if "predictions" in response:
            return response["predictions"]
        return {}


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
            model_name="all-mpnet-base-v2", log=logging
        ).generate_embeddings_async
        return embed, chunk_size

    async def large_local(self):
        chunk_size = 500
        embed = HuggingFaceTextEmbedding(
            model_name="gtr-t5-large", log=logging
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
        embed = OpenAITextEmbedding(
            model_id="text-embedding-ada-002",
            api_key=self.AGENT_CONFIG["settings"]["OPENAI_API_KEY"],
            log=logging,
        ).generate_embeddings_async
        return embed, chunk_size

    async def google_palm(self):
        chunk_size = 1000
        embed = GooglePalmEmbeddingFunction(
            api_key=self.AGENT_CONFIG["settings"]["GOOGLE_API_KEY"],
        )
        return embed, chunk_size

    async def google_vertex(self):
        chunk_size = 1000
        embed = GoogleVertexEmbeddingFunction(
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
