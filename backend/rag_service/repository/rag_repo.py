"""
RAG Repository — pgvector 数据访问

三张表:
  rag_document — 原始文件元信息
  rag_chunk    — 文档分段 + embedding (核心检索表)
  rag_memory   — 个人语义记忆 (习惯/偏好/经验)
"""
import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

VECTOR_DIM = 1024  # BGE-M3 embedding 维度


class RagRepository:
    """RAG 数据访问 — PostgreSQL + pgvector"""

    def __init__(self, conn):
        self.conn = conn

    # ========== Document ==========

    async def create_document(
        self, user_id: int, filename: str, file_type: str = "text",
        source_type: str = "upload", metadata: dict = None,
    ) -> int:
        row = await self.conn.fetchrow(
            "INSERT INTO rag_document (user_id, filename, file_type, source_type, metadata) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            user_id, filename, file_type, source_type,
            json.dumps(metadata or {}, ensure_ascii=False),
        )
        return row["id"]

    async def delete_document(self, doc_id: int) -> int:
        result = await self.conn.execute(
            "DELETE FROM rag_document WHERE id=$1", doc_id
        )
        return int(result.split()[-1]) if result else 0

    # ========== Chunk (核心) ==========

    async def insert_chunks(self, document_id: int, chunks: list[dict]) -> int:
        """
        批量插入 chunk (content + embedding)

        Args:
            document_id: 关联文档 ID
            chunks: [{"content": "...", "embedding": [0.1, 0.2, ...], "metadata": {...}}]

        Returns:
            插入数量
        """
        count = 0
        for i, chunk in enumerate(chunks):
            embedding_str = _format_vector(chunk["embedding"])
            await self.conn.execute(
                "INSERT INTO rag_chunk (document_id, chunk_index, content, embedding, metadata) "
                "VALUES ($1,$2,$3,$4,$5)",
                document_id, i,
                chunk["content"],
                embedding_str,
                json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
            )
            count += 1
        return count

    async def search_chunks(
        self, query_embedding: list[float], top_k: int = 5,
        user_id: int = None, category: str = None,
    ) -> list[dict]:
        """
        向量相似度搜索

        Args:
            query_embedding: 查询向量 (1024维)
            top_k: 返回数量
            user_id: 按用户过滤 (可选)
            category: 按分类过滤 (可选, 如 "course"/"project")

        Returns:
            [{id, content, score, metadata, ...}]
        """
        query_vec = _format_vector(query_embedding)

        conditions = ["1=1"]
        params: list = [query_vec, top_k]

        if user_id:
            conditions.append("d.user_id = $3")
            params.append(user_id)

        if category:
            conditions.append("c.metadata->>'category' = $4")
            params.append(category)

        where = " AND ".join(conditions)

        sql = f"""
            SELECT c.id, c.content, c.metadata, d.filename, d.file_type,
                   1 - (c.embedding <=> $1::vector) AS similarity
            FROM rag_chunk c
            JOIN rag_document d ON c.document_id = d.id
            WHERE {where}
            ORDER BY c.embedding <=> $1::vector
            LIMIT $2
        """

        rows = await self.conn.fetch(sql, *params)
        return [
            {
                "id": r["id"], "content": r["content"],
                "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                "filename": r["filename"], "file_type": r["file_type"],
                "score": round(float(r["similarity"]), 4),
            }
            for r in rows
        ]

    # ========== Memory (语义个人记忆) ==========

    async def save_memory(
        self, user_id: int, content: str, memory_type: str = "general",
        embedding: list[float] = None, confidence: float = 0.5,
        metadata: dict = None,
    ) -> int:
        emb_str = _format_vector(embedding) if embedding else None
        row = await self.conn.fetchrow(
            "INSERT INTO rag_memory (user_id, content, memory_type, confidence, embedding, metadata) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            user_id, content, memory_type, confidence, emb_str,
            json.dumps(metadata or {}, ensure_ascii=False),
        )
        return row["id"]

    async def search_memory(
        self, user_id: int, query_embedding: list[float],
        memory_type: str = None, top_k: int = 5,
    ) -> list[dict]:
        query_vec = _format_vector(query_embedding)

        conditions = ["user_id = $3"]
        params = [query_vec, top_k, user_id]

        if memory_type:
            conditions.append("memory_type = $4")
            params.append(memory_type)

        where = " AND ".join(conditions)

        rows = await self.conn.fetch(
            f"SELECT id, content, memory_type, confidence, metadata, "
            f"1 - (embedding <=> $1::vector) AS similarity "
            f"FROM rag_memory WHERE {where} "
            f"ORDER BY embedding <=> $1::vector LIMIT $2",
            *params,
        )
        return [
            {
                "id": r["id"], "content": r["content"],
                "memory_type": r["memory_type"], "confidence": r["confidence"],
                "score": round(float(r["similarity"]), 4),
            }
            for r in rows
        ]

    async def delete_low_confidence_memories(self, user_id: int, threshold: float = 0.3):
        """清理低置信度的记忆"""
        result = await self.conn.execute(
            "DELETE FROM rag_memory WHERE user_id=$1 AND confidence < $2",
            user_id, threshold,
        )
        return int(result.split()[-1]) if result else 0


def _format_vector(vec: list[float]) -> str:
    """[0.1, 0.2, 0.3] → '[0.1,0.2,0.3]'"""
    return "[" + ",".join(str(v) for v in vec) + "]"


async def get_rag_conn():
    """获取 PostgreSQL 连接"""
    import asyncpg
    from common.config import Settings
    s = Settings()
    return await asyncpg.connect(
        host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
        user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
        database=s.POSTGRES_DB, timeout=5,
    )
