import os
import numpy as np
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2


class Embedding:
    def __init__(self, agent_settings=None):
        self.agent_settings = (
            agent_settings if agent_settings is not None else {"embedder": "default"}
        )
        self.default_embedder = ONNXMiniLM_L6_V2()
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
        try:
            self.embedder = self.embedder_settings[self.agent_settings["embedder"]][
                "embed"
            ]
            self.chunk_size = self.embedder_settings[self.agent_settings["embedder"]][
                "chunk_size"
            ]
        except:
            self.embedder = self.default_embedder
            self.chunk_size = 256

    def get_embedder_settings(self):
        embedder_settings = {
            "default": {
                "chunk_size": 256,
                "embed": self.default_embedder,
            }
        }
        return embedder_settings

    def embed_text(self, text) -> np.ndarray:
        embedding = self.embedder.__call__(input=[text])[0]
        return embedding


def get_embedding_providers():
    embedder_settings = Embedding().get_embedder_settings()
    return list(embedder_settings.keys())


def get_embedders():
    return Embedding().get_embedder_settings()
