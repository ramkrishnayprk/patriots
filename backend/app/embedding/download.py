import logging
import os
from pathlib import Path

from app.embedding.model import LocalFastEmbedModel, model_marker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    model_name = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5").strip()
    destination = Path(os.getenv("EMBEDDING_MODEL_PATH", "/models"))
    marker = model_marker(destination, model_name)
    if marker.is_file():
        logger.info("Embedding model already exists at %s", destination)
        return

    destination.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s once to %s", model_name, destination)
    LocalFastEmbedModel(model_name, destination, local_only=False)
    marker.write_text(model_name + "\n", encoding="utf-8")
    logger.info("Embedding model saved; ingestion can now run fully offline.")


if __name__ == "__main__":
    main()
