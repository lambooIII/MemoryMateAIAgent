import hashlib
import math
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import Settings


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    text: str
    source: str
    score: float | None = None


class VectorRepository(Protocol):
    def upsert(self, chunks: list[KnowledgeChunk], vectors: list[list[float]]) -> int: ...

    def search(self, vector: list[float], limit: int) -> list[KnowledgeChunk]: ...

    def count(self) -> int: ...

    def close(self) -> None: ...


class InMemoryVectorRepository:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[KnowledgeChunk, list[float]]] = {}

    def upsert(self, chunks: list[KnowledgeChunk], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("文本块数量与向量数量不一致")
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._entries[chunk.chunk_id] = (chunk, vector)
        return len(chunks)

    def search(self, vector: list[float], limit: int) -> list[KnowledgeChunk]:
        scored = [
            KnowledgeChunk(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                source=chunk.source,
                score=_cosine_similarity(vector, stored_vector),
            )
            for chunk, stored_vector in self._entries.values()
        ]
        return sorted(scored, key=lambda item: item.score or -1, reverse=True)[:limit]

    def count(self) -> int:
        return len(self._entries)

    def close(self) -> None:
        self._entries.clear()


class MilvusVectorRepository:
    def __init__(self, settings: Settings) -> None:
        from pymilvus import MilvusClient

        kwargs: dict[str, Any] = {"uri": settings.milvus_uri}
        if settings.milvus_token:
            kwargs["token"] = settings.milvus_token
        self._client = MilvusClient(**kwargs)
        self._collection = settings.milvus_collection
        self._dimension = settings.embedding_dimension

        databases = self._client.list_databases()
        if settings.milvus_database not in databases:
            self._client.create_database(db_name=settings.milvus_database)
        self._client.use_database(db_name=settings.milvus_database)
        if not self._client.has_collection(collection_name=self._collection):
            self._client.create_collection(
                collection_name=self._collection,
                dimension=self._dimension,
                metric_type="COSINE",
            )

    def upsert(self, chunks: list[KnowledgeChunk], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("文本块数量与向量数量不一致")
        data = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if len(vector) != self._dimension:
                raise ValueError(
                    f"Embedding 维度为 {len(vector)}，Milvus collection 维度为 {self._dimension}"
                )
            data.append(
                {
                    "id": _stable_int_id(chunk.chunk_id),
                    "vector": vector,
                    "text": chunk.text,
                    "source": chunk.source,
                    "chunk_id": chunk.chunk_id,
                }
            )
        if data:
            self._client.upsert(collection_name=self._collection, data=data)
            self._client.flush(collection_name=self._collection)
        return len(data)

    def search(self, vector: list[float], limit: int) -> list[KnowledgeChunk]:
        results = self._client.search(
            collection_name=self._collection,
            data=[vector],
            limit=limit,
            output_fields=["text", "source", "chunk_id"],
        )
        return [
            KnowledgeChunk(
                chunk_id=str(hit["entity"]["chunk_id"]),
                text=hit["entity"]["text"],
                source=hit["entity"].get("source", "unknown"),
                score=float(hit["distance"]),
            )
            for hit in (results[0] if results else [])
        ]

    def count(self) -> int:
        stats = self._client.get_collection_stats(collection_name=self._collection)
        return int(stats.get("row_count", 0))

    def close(self) -> None:
        self._client.close()


def create_vector_repository(settings: Settings) -> VectorRepository:
    if settings.vector_store_backend == "milvus":
        if not settings.milvus_uri:
            raise ValueError("选择 Milvus 时必须填写 MILVUS_URI")
        return MilvusVectorRepository(settings)
    return InMemoryVectorRepository()


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("向量维度不一致")
    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _stable_int_id(chunk_id: str) -> int:
    digest = hashlib.sha256(chunk_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)

