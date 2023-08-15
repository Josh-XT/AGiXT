import os
import requests
import importlib
import tarfile
import numpy as np
import numpy.typing as npt
from chromadb.utils import embedding_functions
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from typing import List, cast


class ONNXMiniLM_L6_V2(EmbeddingFunction):
    MODEL_NAME = "all-MiniLM-L6-v2"
    DOWNLOAD_PATH = os.getcwd()
    EXTRACTED_FOLDER_NAME = "onnx"
    ARCHIVE_FILENAME = "onnx.tar.gz"
    MODEL_DOWNLOAD_URL = (
        "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
    )
    tokenizer = None
    model = None

    def __init__(self) -> None:
        # Import dependencies on demand to mirror other embedding functions. This
        # breaks typechecking, thus the ignores.
        try:
            # Equivalent to import onnxruntime
            self.ort = importlib.import_module("onnxruntime")
        except ImportError:
            raise ValueError(
                "The onnxruntime python package is not installed. Please install it with `pip install onnxruntime`"
            )
        try:
            # Equivalent to from tokenizers import Tokenizer
            self.Tokenizer = importlib.import_module("tokenizers").Tokenizer
        except ImportError:
            raise ValueError(
                "The tokenizers python package is not installed. Please install it with `pip install tokenizers`"
            )
        try:
            # Equivalent to from tqdm import tqdm
            self.tqdm = importlib.import_module("tqdm").tqdm
        except ImportError:
            raise ValueError(
                "The tqdm python package is not installed. Please install it with `pip install tqdm`"
            )

    # Borrowed from https://gist.github.com/yanqd0/c13ed29e29432e3cf3e7c38467f42f51
    # Download with tqdm to preserve the sentence-transformers experience
    def _download(self, url: str, fname: str, chunk_size: int = 1024) -> None:
        resp = requests.get(url, stream=True)
        total = int(resp.headers.get("content-length", 0))
        with open(fname, "wb") as file, self.tqdm(
            desc=str(fname),
            total=total,
            unit="iB",
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for data in resp.iter_content(chunk_size=chunk_size):
                size = file.write(data)
                bar.update(size)

    # Use pytorches default epsilon for division by zero
    # https://pytorch.org/docs/stable/generated/torch.nn.functional.normalize.html
    def _normalize(self, v: npt.NDArray) -> npt.NDArray:
        norm = np.linalg.norm(v, axis=1)
        norm[norm == 0] = 1e-12
        return v / norm[:, np.newaxis]

    def _forward(self, documents: List[str], batch_size: int = 32) -> npt.NDArray:
        # We need to cast to the correct type because the type checker doesn't know that init_model_and_tokenizer will set the values
        self.tokenizer = cast(self.Tokenizer, self.tokenizer)  # type: ignore
        self.model = cast(self.ort.InferenceSession, self.model)  # type: ignore
        all_embeddings = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            encoded = [self.tokenizer.encode(d) for d in batch]
            input_ids = np.array([e.ids for e in encoded])
            attention_mask = np.array([e.attention_mask for e in encoded])
            onnx_input = {
                "input_ids": np.array(input_ids, dtype=np.int64),
                "attention_mask": np.array(attention_mask, dtype=np.int64),
                "token_type_ids": np.array(
                    [np.zeros(len(e), dtype=np.int64) for e in input_ids],
                    dtype=np.int64,
                ),
            }
            model_output = self.model.run(None, onnx_input)
            last_hidden_state = model_output[0]
            # Perform mean pooling with attention weighting
            input_mask_expanded = np.broadcast_to(
                np.expand_dims(attention_mask, -1), last_hidden_state.shape
            )
            embeddings = np.sum(last_hidden_state * input_mask_expanded, 1) / np.clip(
                input_mask_expanded.sum(1), a_min=1e-9, a_max=None
            )
            embeddings = self._normalize(embeddings).astype(np.float32)
            all_embeddings.append(embeddings)
        return np.concatenate(all_embeddings)

    def _init_model_and_tokenizer(self) -> None:
        if self.model is None and self.tokenizer is None:
            self.tokenizer = self.Tokenizer.from_file(
                os.path.join(
                    self.DOWNLOAD_PATH, self.EXTRACTED_FOLDER_NAME, "tokenizer.json"
                )
            )
            # max_seq_length = 256, for some reason sentence-transformers uses 256 even though the HF config has a max length of 128
            # https://github.com/UKPLab/sentence-transformers/blob/3e1929fddef16df94f8bc6e3b10598a98f46e62d/docs/_static/html/models_en_sentence_embeddings.html#LL480
            self.tokenizer.enable_truncation(max_length=256)
            self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=256)
            self.model = self.ort.InferenceSession(
                os.path.join(
                    self.DOWNLOAD_PATH, self.EXTRACTED_FOLDER_NAME, "model.onnx"
                )
            )

    def __call__(self, texts: Documents) -> Embeddings:
        # Only download the model when it is actually used
        self._download_model_if_not_exists()
        self._init_model_and_tokenizer()
        res = cast(Embeddings, self._forward(texts).tolist())
        return res

    def _download_model_if_not_exists(self) -> None:
        onnx_files = [
            "config.json",
            "model.onnx",
            "special_tokens_map.json",
            "tokenizer_config.json",
            "tokenizer.json",
            "vocab.txt",
        ]
        extracted_folder = os.path.join(self.DOWNLOAD_PATH, self.EXTRACTED_FOLDER_NAME)
        onnx_files_exist = True
        for f in onnx_files:
            if not os.path.exists(os.path.join(extracted_folder, f)):
                onnx_files_exist = False
                break
        # Model is not downloaded yet
        if not onnx_files_exist:
            os.makedirs(self.DOWNLOAD_PATH, exist_ok=True)
            if not os.path.exists(
                os.path.join(self.DOWNLOAD_PATH, self.ARCHIVE_FILENAME)
            ):
                self._download(
                    url=self.MODEL_DOWNLOAD_URL,
                    fname=os.path.join(self.DOWNLOAD_PATH, self.ARCHIVE_FILENAME),
                )
            with tarfile.open(
                name=os.path.join(self.DOWNLOAD_PATH, self.ARCHIVE_FILENAME),
                mode="r:gz",
            ) as tar:
                tar.extractall(path=self.DOWNLOAD_PATH)


class Embedding:
    def __init__(self, agent_settings=None):
        self.agent_settings = (
            agent_settings if agent_settings is not None else {"embedder": "default"}
        )
        self.embedder_settings = self.get_embedder_settings()
        if self.agent_settings["embedder"] not in self.embedder_settings:
            self.agent_settings["embedder"] = "default"
        self.embedder = self.embedder_settings[self.agent_settings["embedder"]]["embed"]
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
        default_embedder = ONNXMiniLM_L6_V2()
        embedder_settings = {
            "default": {
                "chunk_size": 256,
                "embed": default_embedder,
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
                else default_embedder,
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
                else default_embedder,
            },
            "google_palm": {
                "chunk_size": 1000,
                "params": ["GOOGLE_API_KEY"],
                "embed": embedding_functions.GooglePalmEmbeddingFunction(
                    api_key=self.agent_settings["GOOGLE_API_KEY"]
                )
                if "GOOGLE_API_KEY" in self.agent_settings
                else default_embedder,
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
                else default_embedder,
            },
            "cohere": {
                "chunk_size": 500,
                "params": ["COHERE_API_KEY"],
                "embed": embedding_functions.CohereEmbeddingFunction(
                    api_key=self.agent_settings["COHERE_API_KEY"]
                )
                if "COHERE_API_KEY" in self.agent_settings
                else default_embedder,
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
