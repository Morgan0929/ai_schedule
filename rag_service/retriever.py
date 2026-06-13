"""
知识检索器

组合嵌入 + 向量检索，提供高层检索接口
"""
from typing import Any
from rag_service.embeddings import embedding_service
from rag_service.vector_store import vector_store


class KnowledgeRetriever:
    """知识检索器"""

    @staticmethod
    async def retrieve(query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        检索相关知识

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            检索结果列表
        """
        # 1. 将查询转为向量
        query_vector = await embedding_service.encode_single(query)

        # 2. Qdrant 检索
        results = vector_store.search(query_vector, limit=top_k)

        # 3. 格式化返回
        formatted = []
        for r in results:
            formatted.append({
                "id": r.id,
                "score": r.score,
                "payload": r.payload,
            })
        return formatted

    @staticmethod
    async def add_document(title: str, content: str, metadata: dict[str, Any] = None):
        """
        添加文档到知识库

        Args:
            title: 文档标题
            content: 文档内容
            metadata: 元数据
        """
        # 1. 分段（简单按段落分，后续可优化为语义分段）
        chunks = [c.strip() for c in content.split("\n\n") if c.strip()]

        # 2. 嵌入
        embeddings = await embedding_service.encode(chunks)

        # 3. 存入 Qdrant
        from qdrant_client.models import PointStruct
        import uuid

        points = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload={
                    "title": title,
                    "content": chunk,
                    "chunk_index": i,
                    **(metadata or {}),
                },
            ))

        vector_store.upsert(points)


# 全局单例
retriever = KnowledgeRetriever()
