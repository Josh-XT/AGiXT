import os
import numpy as np
from chromadb.utils import embedding_functions


class Embedding:
    def __init__(self, agent_settings=None):
        self.agent_settings = (
            agent_settings if agent_settings is not None else {"embedder": "default"}
        )
        self.default_embedder = embedding_functions.ONNXMiniLM_L6_V2()
        self.default_embedder.DOWNLOAD_PATH = os.getcwd()
        try:
            self.embedder_settings = self.get_embedder_settings()
        except:
            self.embedder_settings = {
                "default": {
                    "chunk_size": 256,
                    "embed": self.default_embedder,
                },
            }
        if (
            "embedder" not in self.agent_settings
            or self.agent_settings["embedder"] not in self.embedder_settings
            or self.agent_settings["embedder"] == "default"
        ):
            self.agent_settings["embedder"] = "default"
            self.embedder = self.default_embedder
            self.chunk_size = 256
        else:
            self.embedder = self.embedder_settings[self.agent_settings["embedder"]][
                "embed"
            ]
            self.chunk_size = self.embedder_settings[self.agent_settings["embedder"]][
                "chunk_size"
            ]

    def get_embedder_settings(self):
        if "API_URI" in self.agent_settings:
            if self.agent_settings["API_URI"] != "":
                api_base = self.agent_settings["API_URI"]
            else:
                api_base = None
        else:
            api_base = None
        embedder_settings = {
            "default": {
                "chunk_size": 256,
                "embed": self.default_embedder,
            },
            "azure": {
                "chunk_size": 1000,
                "params": [
                    "AZURE_API_KEY",
                    "AZURE_DEPLOYMENT_NAME",
                    "AZURE_OPENAI_ENDPOINT",
                ],
                "embed": embedding_functions.OpenAIEmbeddingFunction(
                    api_key=self.agent_settings["AZURE_API_KEY"],
                    organization_id=self.agent_settings["AZURE_DEPLOYMENT_NAME"],
                    api_base=self.agent_settings["AZURE_OPENAI_ENDPOINT"],
                    api_type="azure",
                )
                if "AZURE_API_KEY" in self.agent_settings
                and "AZURE_DEPLOYMENT_NAME" in self.agent_settings
                and "AZURE_OPENAI_ENDPOINT" in self.agent_settings
                else self.default_embedder,
            },
            "openai": {
                "chunk_size": 1000,
                "params": ["OPENAI_API_KEY", "API_URI"],
                "embed": embedding_functions.OpenAIEmbeddingFunction(
                    api_key=self.agent_settings["OPENAI_API_KEY"],
                    model_name="text-embedding-ada-002",
                    api_base=api_base,
                )
                if "OPENAI_API_KEY" in self.agent_settings
                else self.default_embedder,
            },
            "google_vertex": {
                "chunk_size": 1000,
                "params": ["GOOGLE_API_KEY", "GOOGLE_PROJECT_ID"],
                "embed": embedding_functions.GoogleVertexEmbeddingFunction(
                    api_key=self.agent_settings["GOOGLE_API_KEY"],
                    project_id=self.agent_settings["GOOGLE_PROJECT_ID"],
                )
                if "GOOGLE_PROJECT_ID" in self.agent_settings
                and "GOOGLE_API_KEY" in self.agent_settings
                else self.default_embedder,
            },
            "cohere": {
                "chunk_size": 500,
                "params": ["COHERE_API_KEY"],
                "embed": embedding_functions.CohereEmbeddingFunction(
                    api_key=self.agent_settings["COHERE_API_KEY"]
                )
                if "COHERE_API_KEY" in self.agent_settings
                else self.default_embedder,
            },
        }
        return embedder_settings

    def embed_text(self, text) -> np.ndarray:
        embedding = self.embedder.__call__(texts=[text])[0]
        return embedding


def get_embedding_providers():
    embedder_settings = Embedding().get_embedder_settings()
    return list(embedder_settings.keys())


def get_embedders():
    return Embedding().get_embedder_settings()
