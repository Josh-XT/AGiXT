import os
import numpy as np
from chromadb.utils.embedding_functions import (
    ONNXMiniLM_L6_V2,
    GoogleVertexEmbeddingFunction,
)
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from typing import Optional
import openai


class OpenAIEmbeddingFunction(EmbeddingFunction):
    def __init__(
        self,
        api_key: Optional[str] = "",
        model_name: str = "text-embedding-ada-002",
        organization_id: Optional[str] = None,
        api_base: Optional[str] = None,
        api_type: Optional[str] = None,
    ):
        openai.api_key = api_key
        if api_base is not None:
            openai.api_base = api_base
        if api_type is not None:
            openai.api_type = api_type
        if organization_id is not None:
            openai.organization = organization_id
        self._client = openai.Embedding
        self.model_name = model_name

    def __call__(self, texts: Documents) -> Embeddings:
        texts = [t.replace("\n", " ") for t in texts]
        try:
            embeddings = self._client.create(input=texts, model=self.model_name)["data"]
        except:
            embeddings = self._client.create(input=texts, engine=self.model_name)[
                "data"
            ]
        sorted_embeddings = sorted(embeddings, key=lambda e: e["index"])  # type: ignore
        return [result["embedding"] for result in sorted_embeddings]


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
            if "provider" in self.agent_settings:
                if "provider" == "local":
                    self.agent_settings["embedder"] = "local"
                elif "provider" == "azure":
                    self.agent_settings["embedder"] = "azure"
                elif "provider" == "openai":
                    self.agent_settings["embedder"] = "openai"
                elif "provider" == "palm":
                    self.agent_settings["embedder"] = "google_vertex"
                else:
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
            "local": {
                "chunk_size": 1000,
                "params": [
                    "LOCAL_LLM_API_KEY",
                    "AI_MODEL",
                    "API_URI",
                ],
                "embed": OpenAIEmbeddingFunction(
                    model_name=self.agent_settings["AI_MODEL"]
                    if "AI_MODEL" in self.agent_settings
                    else "zephyr-7b-beta",
                    api_key=self.agent_settings["LOCAL_LLM_API_KEY"]
                    if "LOCAL_LLM_API_KEY" in self.agent_settings
                    else None,
                    api_base=self.agent_settings["API_URI"]
                    if "API_URI" in self.agent_settings
                    else "http://localhost:8091/v1",
                ),
            },
            "azure": {
                "chunk_size": 1000,
                "params": [
                    "AZURE_API_KEY",
                    "AZURE_DEPLOYMENT_NAME",
                    "AZURE_OPENAI_ENDPOINT",
                ],
                "embed": OpenAIEmbeddingFunction(
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
                "embed": OpenAIEmbeddingFunction(
                    api_key=self.agent_settings["OPENAI_API_KEY"],
                    model_name="text-embedding-ada-002"
                    if api_base == "https://api.openai.com/v1"
                    else self.agent_settings["AI_MODEL"]
                    if "AI_MODEL" in self.agent_settings
                    else "Mistral-7B-OpenOrca",
                    api_base=api_base,
                )
                if "OPENAI_API_KEY" in self.agent_settings
                else self.default_embedder,
            },
            "google_vertex": {
                "chunk_size": 1000,
                "params": ["GOOGLE_API_KEY", "GOOGLE_PROJECT_ID"],
                "embed": GoogleVertexEmbeddingFunction(
                    api_key=self.agent_settings["GOOGLE_API_KEY"],
                    project_id=self.agent_settings["GOOGLE_PROJECT_ID"],
                )
                if "GOOGLE_PROJECT_ID" in self.agent_settings
                and "GOOGLE_API_KEY" in self.agent_settings
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
