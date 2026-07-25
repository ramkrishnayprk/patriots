import logging
import os
from pathlib import Path

from app.embedding.model import LocalFastEmbedModel, LocalFastEmbedReranker, model_marker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    destination = Path(os.getenv("EMBEDDING_MODEL_PATH", "/models"))
    destination.mkdir(parents=True, exist_ok=True)

    embedding_name = os.getenv(
        "EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5"
    ).strip()
    embedding_marker = model_marker(destination, embedding_name)
    if not embedding_marker.is_file():
        logger.info("Downloading embedding model %s once to %s", embedding_name, destination)
        LocalFastEmbedModel(embedding_name, destination, local_only=False)
        embedding_marker.write_text(embedding_name + "\n", encoding="utf-8")
    else:
        logger.info("Embedding model already exists at %s", destination)

    reranker_name = os.getenv(
        "RERANKER_MODEL_NAME", "Xenova/ms-marco-MiniLM-L-6-v2"
    ).strip()
    reranker_marker = model_marker(destination, reranker_name)
    if not reranker_marker.is_file():
        logger.info("Downloading reranker %s once to %s", reranker_name, destination)
        LocalFastEmbedReranker(reranker_name, destination, local_only=False)
        reranker_marker.write_text(reranker_name + "\n", encoding="utf-8")
    else:
        logger.info("Reranker model already exists at %s", destination)

    logger.info("Retrieval models saved; API inference can run fully offline.")


if __name__ == "__main__":
    main()
