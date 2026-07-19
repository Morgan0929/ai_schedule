"""
Document Processing Pipeline — 分类→提取→切分→Embedding

流程:
  upload → classify → [结构化提取] or [智能切分] → embed → pgvector + SQL
"""
import logging
from rag_service.parser.classifier import DocumentClassifier, DocumentType, ClassificationResult
from rag_service.parser.splitters import get_splitter, SPLITTER_REGISTRY

logger = logging.getLogger(__name__)


class DocumentPipeline:
    """
    文档加工流水线

    Usage:
        pipeline = DocumentPipeline()
        result = await pipeline.process(text, filename, user_id)
        # → chunks: list[dict], structured_data: list[dict]
    """

    def __init__(self):
        pass

    async def process(
        self, text: str, filename: str = "", user_id: int = 0,
        metadata: dict = None,
    ) -> dict:
        """
        完整流水线: classify → split → embed

        Returns:
            {
                "doc_type": "course",
                "confidence": 0.92,
                "chunks": [{"content": "...", "embedding": [...], "metadata": {...}}],
                "structured_data": [{"course": "高数", "time": "09:00", ...}],
                "needs_chunking": False,
            }
        """
        # 1. 分类
        classification = await DocumentClassifier.classify(text, filename, use_llm=False)
        logger.info(
            f"Pipeline classify: {classification.doc_type.value} "
            f"(conf={classification.confidence:.2f}, chunk={classification.needs_chunking})"
        )

        # 2. 选择 Splitter/Extractor
        splitter = get_splitter(classification.doc_type)
        splitter_name = type(splitter).__name__
        logger.info(f"Pipeline splitter: {splitter_name}")

        # 3. 执行切分
        chunks = await splitter.split(text, metadata or {})

        # 4. 分离结构化数据
        structured = []
        regular_chunks = []
        for c in chunks:
            if c.get("metadata", {}).get("structured"):
                structured.append(c)
            else:
                regular_chunks.append(c)

        # 5. Embedding (只对非结构化 chunk)
        if regular_chunks:
            from rag_service.services.rag_service import EmbeddingService
            texts = [c["content"] for c in regular_chunks]
            embeddings = EmbeddingService.encode(texts)
            for i, emb in enumerate(embeddings):
                regular_chunks[i]["embedding"] = emb

        # 结构化数据也做 embedding (用于语义搜索 "之前那个数学作业是什么来着?")
        if structured:
            from rag_service.services.rag_service import EmbeddingService
            texts = [c["content"] for c in structured]
            embeddings = EmbeddingService.encode(texts)
            for i, emb in enumerate(embeddings):
                structured[i]["embedding"] = emb

        return {
            "doc_type": classification.doc_type.value,
            "confidence": classification.confidence,
            "chunks": regular_chunks + structured,
            "structured_count": len(structured),
            "regular_count": len(regular_chunks),
            "needs_chunking": classification.needs_chunking,
        }

    @staticmethod
    def get_supported_types() -> list[str]:
        return [t.value for t in DocumentType]


# Global singleton
pipeline = DocumentPipeline()
