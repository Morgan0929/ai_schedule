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
    """
    BGE-M3 嵌入服务 (1024维)

    加载顺序:
      1. HuggingFaceBgeEmbeddings (langchain_community, 推荐)
      2. SentenceTransformer (直接调用)
      3. Fallback (字符特征, 零依赖)

    属于 RAG Infrastructure 层 — Agent 不直接调用, 通过 Retriever 间接使用。
    换模型只改这里。
    """

    _model = None

    @classmethod
    def _load_model(cls):
        if cls._model is not None:
            return

        # 方式 1: LangChain 封装 (推荐)
        try:
            from langchain_community.embeddings import HuggingFaceBgeEmbeddings
            cls._model = HuggingFaceBgeEmbeddings(
                model_name="BAAI/bge-m3",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
            logger.info("BGE-M3 loaded via langchain_community (1024d)")
            return
        except Exception as e:
            logger.debug(f"langchain_community BGE failed: {e}")

        # 方式 2: 直接 sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            cls._model = SentenceTransformer("BAAI/bge-m3")
            logger.info("BGE-M3 loaded via sentence-transformers (1024d)")
            return
        except Exception as e:
            logger.debug(f"SentenceTransformer failed: {e}")

        # 方式 3: Fallback
        cls._model = "fallback"
        logger.warning("BGE-M3 unavailable, using character fallback")

    @classmethod
    def encode(cls, texts: list[str]) -> list[list[float]]:
        cls._load_model()
        if cls._model == "fallback":
            return cls._fallback_encode(texts)
        # HuggingFaceBgeEmbeddings 用 embed_documents
        if hasattr(cls._model, "embed_documents"):
            return cls._model.embed_documents(texts)
        # SentenceTransformer 用 encode → tolist
        embeddings = cls._model.encode(texts, normalize_embeddings=True)
        if hasattr(embeddings, "tolist"):
            return embeddings.tolist()
        return list(embeddings)

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
    @staticmethod
    def get_stats() -> dict:
        """Return lightweight RAG service status without opening a DB connection."""
        return {
            "embedding_dim": EmbeddingService.dimension(),
            "backend": "pgvector",
            "channels": ["document", "memory"],
        }

    """RAG 服务 — Document + Memory 双通道"""

    @staticmethod
    async def upload_document(
        user_id: int, filename: str, content: str,
        file_type: str = "text", source_type: str = "upload",
        metadata: dict = None,
    ) -> dict:
        """
        上传文档 → 分类 → 选择Splitter → 结构化提取/chunk → embedding → 入库

        不同类型不同处理:
          - 课程表 → 结构化提取 (不chunk)
          - 作业通知 → 提取事件 (不chunk)
          - 会议纪要 → 按标题切
          - 通用文档 → RecursiveTextSplitter (800/150)
        """
        from rag_service.repository.rag_repo import RagRepository, get_rag_conn
        from rag_service.parser.pipeline import DocumentPipeline

        conn = await get_rag_conn()
        try:
            repo = RagRepository(conn)

            # Pipeline: classify → split → embed
            pipeline = DocumentPipeline()
            result = await pipeline.process(content, filename, user_id, metadata)

            # 创建文档记录
            doc_id = await repo.create_document(
                user_id, filename,
                file_type=result["doc_type"],
                source_type=source_type,
                metadata={
                    **(metadata or {}),
                    "classifier_confidence": result["confidence"],
                    "structured_items": result["structured_count"],
                },
            )

            # 入库 chunks
            count = await repo.insert_chunks(doc_id, result["chunks"])

            # 结构化数据处理
            structured_tasks = []
            if result["structured_count"] > 0:
                structured_tasks = await _process_structured_data(
                    user_id, result["chunks"], result["doc_type"]
                )

            logger.info(
                f"RAG upload: doc={doc_id} type={result['doc_type']} "
                f"chunks={count} structured={result['structured_count']}"
            )

            return {
                "document_id": doc_id,
                "chunks": count,
                "filename": filename,
                "doc_type": result["doc_type"],
                "confidence": result["confidence"],
                "structured_items": result["structured_count"],
                "tasks_created": len(structured_tasks),
            }
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


async def _process_structured_data(
    user_id: int, chunks: list[dict], doc_type: str
) -> list[dict]:
    """
    将结构化提取的数据路由到对应的业务系统

    course → 创建 schedule 条目
    assignment → 创建 task
    """
    tasks = []
    for chunk in chunks:
        md = chunk.get("metadata", {})
        if not md.get("structured"):
            continue

        if doc_type == "course":
            # 创建 schedule 条目
            tasks.append({"action": "schedule", "data": md})
        elif doc_type == "assignment":
            # 自动创建任务
            tasks.append({"action": "task", "data": md})
        elif doc_type == "meeting" and md.get("section_type") == "todo":
            tasks.append({"action": "task", "data": md})

    return tasks
