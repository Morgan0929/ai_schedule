"""
向量存储 — Qdrant + 内存回退双模式
"""
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Any

from common.config import settings

logger = logging.getLogger(__name__)


@dataclass
class VectorPoint:
    id: str
    vector: np.ndarray
    payload: dict[str, Any] = field(default_factory=dict)


class MemoryVectorStore:
    """内存向量存储 — 无需 Docker"""

    def __init__(self):
        self.points: dict[str, VectorPoint] = {}

    def upsert(self, points: list[dict]):
        for p in points:
            vec = np.array(p["vector"], dtype=np.float32)
            self.points[p["id"]] = VectorPoint(id=p["id"], vector=vec, payload=p.get("payload", {}))

    def search(self, query_vector: list[float], limit: int = 5) -> list[dict]:
        if not self.points:
            return []
        query = np.array(query_vector, dtype=np.float32)
        results = []
        for point in self.points.values():
            dot = np.dot(query, point.vector)
            nq = np.linalg.norm(query)
            npv = np.linalg.norm(point.vector)
            score = float(dot / (nq * npv)) if nq > 0 and npv > 0 else 0.0
            results.append({"id": point.id, "score": score, "payload": point.payload})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def delete(self, point_ids: list[str]):
        for pid in point_ids:
            self.points.pop(pid, None)

    def count(self) -> int:
        return len(self.points)


class VectorStore:
    """向量存储门面"""

    def __init__(self):
        self._store = None

    def _init_store(self):
        if self._store is not None:
            return
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            client = QdrantClient(
                host=settings.QDRANT_HOST, port=settings.QDRANT_PORT,
                api_key=settings.QDRANT_API_KEY or None,
            )
            collections = client.get_collections()
            names = [c.name for c in collections.collections]
            if "ai_schedule_knowledge" not in names:
                client.create_collection(
                    collection_name="ai_schedule_knowledge",
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                )
            self._store = client
            logger.info("VectorStore: Qdrant connected")
            return
        except Exception as e:
            logger.info(f"Qdrant unavailable ({e}), using in-memory store")
        self._store = MemoryVectorStore()
        logger.info("VectorStore: in-memory mode")

    def upsert(self, points: list[dict]):
        self._init_store()
        if isinstance(self._store, MemoryVectorStore):
            self._store.upsert(points)
        else:
            from qdrant_client.models import PointStruct
            qpoints = [
                PointStruct(id=p["id"], vector=p["vector"], payload=p.get("payload", {}))
                for p in points
            ]
            self._store.upsert(collection_name="ai_schedule_knowledge", points=qpoints)

    def search(self, query_vector: list[float], limit: int = 5) -> list[dict]:
        self._init_store()
        if isinstance(self._store, MemoryVectorStore):
            return self._store.search(query_vector, limit)
        else:
            results = self._store.search(
                collection_name="ai_schedule_knowledge",
                query_vector=query_vector, limit=limit,
            )
            return [{"id": r.id, "score": r.score, "payload": r.payload} for r in results]

    def delete(self, point_ids: list[str]):
        self._init_store()
        if isinstance(self._store, MemoryVectorStore):
            self._store.delete(point_ids)
        else:
            self._store.delete(collection_name="ai_schedule_knowledge", points_selector=point_ids)

    def count(self) -> int:
        self._init_store()
        if isinstance(self._store, MemoryVectorStore):
            return self._store.count()
        else:
            info = self._store.get_collection("ai_schedule_knowledge")
            return info.points_count


vector_store = VectorStore()
