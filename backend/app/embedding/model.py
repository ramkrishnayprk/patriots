import hashlib
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np


def model_marker(cache_dir: Path, model_name: str) -> Path:
    digest = hashlib.sha256(model_name.encode()).hexdigest()[:16]
    return cache_dir / f".ready-{digest}"


def is_model_installed(cache_dir: Path, model_name: str) -> bool:
    return model_marker(cache_dir, model_name).is_file()


class LocalFastEmbedModel:
    max_seq_length = 512

    def __init__(self, model_name: str, cache_dir: Path, *, local_only: bool):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(
            model_name=model_name,
            cache_dir=str(cache_dir),
            local_files_only=local_only,
        )
        descriptions = {item["model"]: item for item in TextEmbedding.list_supported_models()}
        self._dimension = int(descriptions[model_name]["dim"])
        self.tokenizer = _ApproximateTokenizer()

    def eval(self) -> "LocalFastEmbedModel":
        return self

    def get_sentence_embedding_dimension(self) -> int:
        return self._dimension

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int = 64,
        normalize_embeddings: bool = True,
        **_kwargs: Any,
    ) -> np.ndarray:
        vectors = np.asarray(
            list(self._model.embed(texts, batch_size=batch_size)),
            dtype=np.float32,
        )
        if normalize_embeddings:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / np.maximum(norms, np.finfo(np.float32).eps)
        return vectors


class _ApproximateTokenizer:
    @staticmethod
    def encode(text: str, **_kwargs: Any) -> list[int]:
        return list(range(math.ceil(len(text) / 4)))


@lru_cache(maxsize=4)
def load_local_model(model_path: Path, *, model_name: str, device: str) -> LocalFastEmbedModel:
    if device not in {"auto", "cpu"}:
        raise ValueError("This image supports CPU embeddings; set device to auto or cpu.")
    if not is_model_installed(model_path, model_name):
        raise FileNotFoundError(
            f"Embedding model {model_name} is not installed in {model_path}. "
            "Run the embedding-model-download Docker service first."
        )
    model = LocalFastEmbedModel(model_name, model_path, local_only=True)
    model.eval()
    return model


class LocalFastEmbedReranker:
    def __init__(self, model_name: str, cache_dir: Path, *, local_only: bool):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._model = TextCrossEncoder(
            model_name=model_name,
            cache_dir=str(cache_dir),
            local_files_only=local_only,
        )

    def rerank(self, query: str, documents: list[str], *, batch_size: int = 64) -> list[float]:
        return [float(score) for score in self._model.rerank(query, documents, batch_size)]


@lru_cache(maxsize=4)
def load_local_reranker(
    model_path: Path, *, model_name: str
) -> LocalFastEmbedReranker:
    if not is_model_installed(model_path, model_name):
        raise FileNotFoundError(
            f"Reranker model {model_name} is not installed in {model_path}. "
            "Run the embedding-model-download Docker service first."
        )
    return LocalFastEmbedReranker(model_name, model_path, local_only=True)
