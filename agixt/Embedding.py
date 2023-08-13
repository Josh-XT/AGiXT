import os
import spacy
import requests
import importlib
import tarfile
import numpy as np
import numpy.typing as npt
from chromadb.utils import embedding_functions
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from pathlib import Path
from typing import List, cast

HOME_DIR = os.getcwd()


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


class ONNX(EmbeddingFunction):
    # https://github.com/python/mypy/issues/7291 mypy makes you type the constructor if
    # no args
    def __init__(
        self,
        MODEL_NAME: str = "all-MiniLM-L6-v2",
        DOWNLOAD_PATH: str = HOME_DIR,
        EXTRACTED_FOLDER_NAME="onnx",
        ARCHIVE_FILENAME="onnx.tar.gz",
        MODEL_DOWNLOAD_URL=(
            "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
        ),
        tokenizer=None,
        model=None,
    ) -> None:
        # Import dependencies on demand to mirror other embedding functions. This
        # breaks typechecking, thus the ignores.
        self.MODEL_NAME = MODEL_NAME if MODEL_NAME else "all-MiniLM-L6-v2"
        self.DOWNLOAD_PATH = DOWNLOAD_PATH if DOWNLOAD_PATH else HOME_DIR
        self.EXTRACTED_FOLDER_NAME = (
            EXTRACTED_FOLDER_NAME if EXTRACTED_FOLDER_NAME else "onnx"
        )
        self.ARCHIVE_FILENAME = ARCHIVE_FILENAME if ARCHIVE_FILENAME else "onnx.tar.gz"
        self.MODEL_DOWNLOAD_URL = (
            MODEL_DOWNLOAD_URL
            if MODEL_DOWNLOAD_URL
            else "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
        )
        self.tokenizer = tokenizer
        self.model = model
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
    def _download(self, url: str, fname: Path, chunk_size: int = 1024) -> None:
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
        # Model is not downloaded yet
        if not os.path.exists(
            os.path.join(self.DOWNLOAD_PATH, self.EXTRACTED_FOLDER_NAME, "model.onnx")
        ):
            os.makedirs(self.DOWNLOAD_PATH, exist_ok=True)
            if not os.path.exists(self.DOWNLOAD_PATH / self.ARCHIVE_FILENAME):
                self._download(
                    self.MODEL_DOWNLOAD_URL, self.DOWNLOAD_PATH / self.ARCHIVE_FILENAME
                )
            with tarfile.open(
                self.DOWNLOAD_PATH / self.ARCHIVE_FILENAME, "r:gz"
            ) as tar:
                tar.extractall(self.DOWNLOAD_PATH)


def get_embedder(agent_settings):
    try:
        embedder = agent_settings["embedder"]
    except:
        embedder = "default"
    if embedder == "default":
        chunk_size = 256
        embed = ONNX()
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

    def embed_text(self, text) -> np.ndarray:
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
