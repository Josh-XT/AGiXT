from Config.Agent import Agent
from chromadb.utils import embedding_functions
import requests
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


class Embedding(Agent):
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

    def google_palm(self):
        self.MAX_EMBEDDING_TOKENS = 3072
        self.EMBEDDING_AGENT = GooglePalmEmbeddingFunction(
            api_key=self.CFG.AGENT_CONFIG["settings"]["GOOGLE_API_KEY"],
        )

    def google_vertex(self):
        self.MAX_EMBEDDING_TOKENS = 3072
        self.EMBEDDING_AGENT = GoogleVertexEmbeddingFunction(
            api_key=self.CFG.AGENT_CONFIG["settings"]["GOOGLE_API_KEY"],
        )


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
