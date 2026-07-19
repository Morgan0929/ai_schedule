"""
RAG Service — PostgreSQL + pgvector + BGE-M3

架构:
  Document RAG: 文件上传→分段→embedding→rag_chunk→向量搜索
  Memory RAG:   对话提取→embedding→rag_memory→语义检索

Retriever 抽象: 今天 pgvector, 以后换 Qdrant 不改上层
"""
import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    """BGE-M3 嵌入服务 (1024维) / 回退 fallback"""

    _model = None

    @classmethod
    def _load_model(cls):
        if cls._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                cls._model = SentenceTransformer("BAAI/bge-m3")
                logger.info("BGE-M3 loaded (1024d)")
            except Exception:
                cls._model = "fallback"
                logger.warning("BGE-M3 unavailable, using fallback")

    @classmethod
    def encode(cls, texts: list[str]) -> list[list[float]]:
        cls._load_model()
        if cls._model == "fallback":
            return cls._fallback_encode(texts)
        embeddings = cls._model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    @classmethod
    def _fallback_encode(cls, texts: list[str]) -> list[list[float]]:
        import numpy as np
        vectors = []
        for text in texts:
            vec = np.zeros(1024, dtype=np.float32)
            for i, c in enumerate(text[:2000]):
                vec[hash(c) % 1024] += 1.0 / (1.0 + i * 0.001)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vectors.append(vec.tolist())
        return vectors

    @classmethod
    def dimension(cls) -> int:
        return 1024


class RagService:
    """RAG 服务 — Document + Memory 双通道"""

    @staticmethod
    async def upload_document(
        user_id: int, filename: str, content: str,
        file_type: str = "text", source_type: str = "upload",
        metadata: dict = None, chunk_size: int = 500,
    ) -> dict:
        from rag_service.repository.rag_repo import RagRepository, get_rag_conn
        conn = await get_rag_conn()
        try:
            repo = RagRepository(conn)
            doc_id = await repo.create_document(user_id, filename, file_type, source_type, metadata)
            chunks = _split_text(content, chunk_size)
            texts = [c["content"] for c in chunks]
            embeddings = EmbeddingService.encode(texts)
            for i, emb in enumerate(embeddings):
                chunks[i]["embedding"] = emb
                chunks[i]["metadata"] = chunks[i].get("metadata", {})
                chunks[i]["metadata"].update(metadata or {})
            count = await repo.insert_chunks(doc_id, chunks)
            return {"document_id": doc_id, "chunks": count, "filename": filename}
        finally:
            await conn.close()

    @staticmethod
    async def search_documents(
        user_id: int, query: str, top_k: int = 5, category: str = None,
    ) -> list[dict]:
        from rag_service.repository.rag_repo import RagRepository, get_rag_conn
        emb = EmbeddingService.encode([query])[0]
        conn = await get_rag_conn()
        try:
            return await RagRepository(conn).search_chunks(emb, top_k, user_id, category)
        finally:
            await conn.close()

    @staticmethod
    async def save_semantic_memory(
        user_id: int, content: str, memory_type: str = "general",
        confidence: float = 0.5, metadata: dict = None,
    ) -> dict:
        from rag_service.repository.rag_repo import RagRepository, get_rag_conn
        emb = EmbeddingService.encode([content])[0]
        conn = await get_rag_conn()
        try:
            mid = await RagRepository(conn).save_memory(user_id, content, memory_type, emb, confidence, metadata)
            return {"memory_id": mid, "type": memory_type, "confidence": confidence}
        finally:
            await conn.close()

    @staticmethod
    async def search_semantic_memory(
        user_id: int, query: str, memory_type: str = None, top_k: int = 5,
    ) -> list[dict]:
        from rag_service.repository.rag_repo import RagRepository, get_rag_conn
        emb = EmbeddingService.encode([query])[0]
        conn = await get_rag_conn()
        try:
            return await RagRepository(conn).search_memory(user_id, emb, memory_type, top_k)
        finally:
            await conn.close()

    @staticmethod
    async def cleanup_memories(user_id: int, min_confidence: float = 0.3) -> int:
        from rag_service.repository.rag_repo import RagRepository, get_rag_conn
        conn = await get_rag_conn()
        try:
            return await RagRepository(conn).delete_low_confidence_memories(user_id, min_confidence)
        finally:
            await conn.close()


def _split_text(text: str, chunk_size: int = 500) -> list[dict]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            chunks.append({"content": para, "metadata": {}})
        else:
            sentences = para.replace("。", "。\n").replace("！", "！\n").split("\n")
            buffer = ""
            for s in sentences:
                if len(buffer) + len(s) > chunk_size and buffer:
                    chunks.append({"content": buffer.strip(), "metadata": {}})
                    buffer = s
                else:
                    buffer += s
            if buffer.strip():
                chunks.append({"content": buffer.strip(), "metadata": {}})
    return chunks
