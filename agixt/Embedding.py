import spacy
import requests
from chromadb.utils import embedding_functions
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from numpy import ndarray


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


def get_embedder(agent_settings):
    try:
        embedder = agent_settings["embedder"]
    except:
        embedder = "default"
    if embedder == "default":
        chunk_size = 128
        embed = embedding_functions.ONNXMiniLM_L6_V2()
    elif embedder == "azure":
        chunk_size = 1000
        embed = embedding_functions.OpenAIEmbeddingFunction(
            api_key=agent_settings["AZURE_API_KEY"],
            organization_id=agent_settings["AZURE_DEPLOYMENT_NAME"],
            api_base=agent_settings["AZURE_OPENAI_ENDPOINT"],
            api_type="azure",
        )
    elif embedder == "openai":
        chunk_size = 1000
        if "API_URI" in agent_settings:
            if agent_settings["API_URI"] != "":
                api_base = agent_settings["API_URI"]
            else:
                api_base = None
        else:
            api_base = None
        embed = embedding_functions.OpenAIEmbeddingFunction(
            api_key=agent_settings["OPENAI_API_KEY"],
            model_name="text-embedding-ada-002",
            api_base=api_base,
        )
    elif embedder == "google_palm":
        chunk_size = 1000
        embed = embedding_functions.GooglePalmEmbeddingFunction(
            api_key=agent_settings["GOOGLE_API_KEY"],
        )
    elif embedder == "google_vertex":
        chunk_size = 1000
        embed = embedding_functions.GoogleVertexEmbeddingFunction(
            api_key=agent_settings["GOOGLE_API_KEY"],
            project_id=agent_settings["GOOGLE_PROJECT_ID"],
        )
    elif embedder == "cohere":
        chunk_size = 500
        embed = embedding_functions.CohereEmbeddingFunction(
            api_key=agent_settings["COHERE_API_KEY"],
        )
    elif embedder == "llamacpp":
        chunk_size = 250
        embed = LlamacppEmbeddingFunction(
            model_name=agent_settings["EMBEDDING_URI"],
        )
    else:
        raise Exception("Embedding function not found")
    return embed, chunk_size


class Embedding:
    def __init__(self, AGENT_CONFIG=None):
        self.AGENT_CONFIG = AGENT_CONFIG
        self.embedder, self.chunk_size = get_embedder(
            agent_settings=AGENT_CONFIG["settings"]
        )

    def embed_text(self, text) -> ndarray:
        embedding = self.embedder.__call__(texts=[text])[0]
        return embedding


def get_embedding_providers():
    return [
        "default",  # SentenceTransformer
        "large_local",  # SentenceTransformer
        "azure",  # OpenAI
        "openai",  # OpenAI
        "google_palm",  # Google
        "google_vertex",  # Google
        "cohere",  # Cohere
        "llamacpp",  # Llamacpp
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
