"""
知识检索器 — 文档分段 + 嵌入 + 检索
"""
import uuid
import logging
from typing import Any
from rag_service.embeddings import embedding_service
from rag_service.vector_store import vector_store

logger = logging.getLogger(__name__)


class DocumentChunker:
    """文档分段器"""

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """
        将长文本按段落/字符数分段

        Args:
            text: 原始文本
            chunk_size: 每段最大字符数
            overlap: 段落重叠字符数

        Returns:
            分段列表
        """
        if not text.strip():
            return []

        # 先按段落分
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) < chunk_size:
                current = (current + "\n" + para).strip()
            else:
                if current:
                    chunks.append(current)
                # 如果单段超过 chunk_size，按字符切分
                if len(para) > chunk_size:
                    for i in range(0, len(para), chunk_size - overlap):
                        chunk = para[i:i + chunk_size]
                        if chunk:
                            chunks.append(chunk)
                else:
                    current = para

        if current:
            chunks.append(current)

        return chunks if chunks else [text[:chunk_size]]


class KnowledgeRetriever:
    """知识检索器 — 组合嵌入 + 向量检索"""

    @staticmethod
    async def add_document(
        title: str, content: str, doc_type: str = "GENERAL",
        metadata: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        添加文档到知识库

        流程: 分段 → 嵌入 → 存入向量库
        """
        # 1. 分段
        chunks = DocumentChunker.chunk_text(content)

        # 2. 嵌入
        embeddings = embedding_service.encode(chunks)

        # 3. 构建向量点
        points = []
        chunk_ids = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            cid = str(uuid.uuid4())[:12]
            chunk_ids.append(cid)
            points.append({
                "id": cid,
                "vector": emb,
                "payload": {
                    "title": title,
                    "content": chunk,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "doc_type": doc_type,
                    **(metadata or {}),
                },
            })

        # 4. 存储
        vector_store.upsert(points)
        logger.info(f"Document '{title}' added: {len(chunks)} chunks")

        return {
            "title": title,
            "chunks": len(chunks),
            "chunk_ids": chunk_ids,
        }

    @staticmethod
    async def search(query: str, top_k: int = 5, min_score: float = 0.0) -> list[dict[str, Any]]:
        """
        搜索知识库

        Args:
            query: 查询文本
            top_k: 返回数量
            min_score: 最低相似度阈值

        Returns:
            按相似度排序的结果列表
        """
        # 1. 查询嵌入
        query_vector = embedding_service.encode_single(query)

        # 2. 向量检索
        results = vector_store.search(query_vector, limit=top_k * 2)

        # 3. 过滤 + 去重（同一文档只保留最相关的一段）
        seen_titles = set()
        filtered = []
        for r in results:
            if r["score"] < min_score:
                continue
            title = r["payload"].get("title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            filtered.append({
                "id": r["id"],
                "score": round(r["score"], 4),
                "title": title,
                "content": r["payload"].get("content", "")[:300],
                "doc_type": r["payload"].get("doc_type", ""),
                "chunk_index": r["payload"].get("chunk_index", 0),
            })
            if len(filtered) >= top_k:
                break

        return filtered

    @staticmethod
    async def delete_document(title: str) -> int:
        """删除文档（按标题匹配）"""
        # 搜索所有匹配的块并删除
        results = vector_store.search(embedding_service.encode_single(title), limit=100)
        ids = [r["id"] for r in results if r["payload"].get("title") == title]
        if ids:
            vector_store.delete(ids)
        return len(ids)

    @staticmethod
    def get_stats() -> dict:
        """获取知识库统计"""
        return {
            "total_vectors": vector_store.count(),
            "embedding_dim": embedding_service.dimension,
        }


retriever = KnowledgeRetriever()
