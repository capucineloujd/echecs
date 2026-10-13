import pytest
from pymilvus import MilvusException

from app.core.errors import VectorStoreError
from app.services.vector_store import VectorStoreService


class MissingCollectionClient:
    def search(self, *args, **kwargs):
        raise MilvusException(code=100, message="collection not found[database=default][collection=opening_chunks]")


def test_missing_collection_explains_how_to_ingest():
    store = VectorStoreService("http://milvus:19530", "opening_chunks")
    store._client = MissingCollectionClient()
    with pytest.raises(VectorStoreError, match="lancer l'ingestion"):
        store.search([0.0] * 1024, top_k=3)
