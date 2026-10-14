import asyncio
import logging

import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, model_name: str, batch_size: int = 16, threads: int = 4, query_instruction: str = ""):
        logger.info("Chargement du modèle d'embedding %s", model_name)
        torch.set_num_threads(threads)
        # float32 forcé : le modèle est stocké en bfloat16, très lent sur CPU
        self._model = SentenceTransformer(model_name, device="cpu", model_kwargs={"dtype": torch.float32})
        self._batch_size = batch_size
        self._query_instruction = query_instruction

    @property
    def dimension(self) -> int:
        return self._model.get_embedding_dimension()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, batch_size=self._batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > 50
        )
        return vectors.tolist()

    def embed_query(self, query: str) -> list[float]:
        vector = self._model.encode(query, prompt=self._query_instruction or None, normalize_embeddings=True)
        return vector.tolist()

    async def aembed_query(self, query: str) -> list[float]:
        return await asyncio.to_thread(self.embed_query, query)
