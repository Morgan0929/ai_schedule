"""
Qdrant 向量数据库客户端

负责向量存储和检索
"""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from common.config import settings


class VectorStore:
    """Qdrant 向量存储"""

    COLLECTION_NAME = "ai_schedule_knowledge"

    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY or None,
        )

    def ensure_collection(self):
        """确保集合存在，不存在则创建"""
        collections = self.client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if self.COLLECTION_NAME not in collection_names:
            self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=1024,          # BGE-M3 向量维度
                    distance=Distance.COSINE,
                ),
            )

    def upsert(self, points: list[PointStruct]):
        """插入或更新向量点"""
        self.ensure_collection()
        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=points,
        )

    def search(self, query_vector: list[float], limit: int = 5) -> list:
        """
        向量相似度搜索

        Args:
            query_vector: 查询向量
            limit: 返回数量

        Returns:
            相似文档列表
        """
        self.ensure_collection()
        results = self.client.search(
            collection_name=self.COLLECTION_NAME,
            query_vector=query_vector,
            limit=limit,
        )
        return results

    def delete(self, point_ids: list[int | str]):
        """删除向量点"""
        self.client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=point_ids,
        )


# 全局单例
vector_store = VectorStore()
