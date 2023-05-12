from Config.Agent import Agent
from chromadb.utils import embedding_functions
import requests
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from typing import Optional


class Embedding(Agent):
    def __init__(self, AGENT_NAME: str = "Agent-LLM"):
        super().__init__(AGENT_NAME)
        self.default()

    def default(self):
        self.MAX_EMBEDDING_TOKENS = 384
        self.EMBEDDING_AGENT = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-mpnet-base-v2"
        )

    def roberta(self):
        self.MAX_EMBEDDING_TOKENS = 512
        self.EMBEDDING_AGENT = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="roberta-base"
        )

    def openai(self):
        self.MAX_EMBEDDING_TOKENS = 2048
        self.EMBEDDING_AGENT = embedding_functions.OpenAIEmbeddingFunction(
            api_key=self.CFG.AGENT_CONFIG["settings"]["OPENAI_API_KEY"],
        )


class GoogleGeckoEmbeddingFunction(EmbeddingFunction):
    def __init__(
        self,
        api_key: str,
        model_name: str = "textembedding-gecko-001",
        project_id: str = "cloud-large-language-models",
    ):
        self._api_url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project_id}/locations/us-central1/endpoints/{model_name}:predict"
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {api_key}"})

    def __call__(self, texts: Documents) -> Embeddings:
        respnonse = self._session.post(
            self._api_url, json={"instances": [{"content": texts}]}
        ).json()

        if "predictions" in respnonse:
            predictions = respnonse["predictions"]
            if len(predictions) > 0 and "embedding" in predictions[0]:
                embedding = predictions[0]["embedding"]
                return embedding
