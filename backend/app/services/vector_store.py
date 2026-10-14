import asyncio
import logging

from pymilvus import DataType, MilvusClient, MilvusException

from app.core.errors import VectorStoreError

logger = logging.getLogger(__name__)

COLLECTION_NOT_FOUND = 100

OUTPUT_FIELDS = ["opening_slug", "opening_name", "eco", "fen", "section", "source", "lang", "url", "text"]


class VectorStoreService:
    def __init__(self, uri: str, collection: str):
        self._uri = uri
        self._collection = collection
        self._client: MilvusClient | None = None

    @property
    def client(self) -> MilvusClient:
        if self._client is None:
            try:
                self._client = MilvusClient(uri=self._uri, timeout=10)
            except MilvusException as exc:
                raise VectorStoreError(f"Milvus injoignable ({self._uri})") from exc
        return self._client

    def recreate_collection(self, dimension: int) -> None:
        if self.client.has_collection(self._collection):
            self.client.drop_collection(self._collection)

        schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dimension)
        schema.add_field("opening_slug", DataType.VARCHAR, max_length=64)
        schema.add_field("opening_name", DataType.VARCHAR, max_length=128)
        schema.add_field("eco", DataType.VARCHAR, max_length=8)
        schema.add_field("fen", DataType.VARCHAR, max_length=128)
        schema.add_field("section", DataType.VARCHAR, max_length=512)
        schema.add_field("source", DataType.VARCHAR, max_length=32)
        schema.add_field("lang", DataType.VARCHAR, max_length=8)
        schema.add_field("url", DataType.VARCHAR, max_length=1024)
        schema.add_field("text", DataType.VARCHAR, max_length=8192)

        index = MilvusClient.prepare_index_params()
        index.add_index("vector", index_type="HNSW", metric_type="COSINE", params={"M": 16, "efConstruction": 200})
        index.add_index("opening_slug", index_type="INVERTED")

        self.client.create_collection(self._collection, schema=schema, index_params=index)

    def insert(self, rows: list[dict]) -> int:
        result = self.client.insert(self._collection, rows)
        return result["insert_count"]

    def count(self) -> int:
        stats = self.client.get_collection_stats(self._collection)
        return int(stats["row_count"])

    def search(self, vector: list[float], top_k: int, opening_slug: str | None = None) -> list[dict]:
        filter_expr = f'opening_slug == "{opening_slug}"' if opening_slug else ""
        try:
            results = self.client.search(
                self._collection,
                data=[vector],
                limit=top_k,
                filter=filter_expr,
                output_fields=OUTPUT_FIELDS,
                search_params={"metric_type": "COSINE", "params": {"ef": 64}},
            )
        except MilvusException as exc:
            if exc.code == COLLECTION_NOT_FOUND:
                raise VectorStoreError(
                    f"Collection '{self._collection}' absente : lancer l'ingestion (python -m scripts.ingest, voir README)"
                ) from exc
            raise VectorStoreError(f"Recherche Milvus impossible : {exc}") from exc
        return [{"score": hit["distance"], **hit["entity"]} for hit in results[0]]

    async def asearch(self, vector: list[float], top_k: int, opening_slug: str | None = None) -> list[dict]:
        return await asyncio.to_thread(self.search, vector, top_k, opening_slug)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
