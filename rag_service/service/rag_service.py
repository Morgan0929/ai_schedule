"""
RAG 业务逻辑层
"""
import logging
from rag_service.retriever import retriever
from rag_service.models import DocumentUploadRequest, DocumentDTO, SearchResultDTO

logger = logging.getLogger(__name__)


class RagService:
    """RAG 知识库服务"""

    @staticmethod
    async def upload_document(request: DocumentUploadRequest) -> DocumentDTO:
        """上传文档"""
        result = await retriever.add_document(
            title=request.title,
            content=request.content,
            doc_type=request.doc_type,
            metadata=request.metadata,
        )
        return DocumentDTO(
            title=result["title"],
            chunks=result["chunks"],
            chunk_ids=result["chunk_ids"],
        )

    @staticmethod
    async def search(query: str, top_k: int = 5, min_score: float = 0.0) -> list[SearchResultDTO]:
        """搜索知识库"""
        results = await retriever.search(query, top_k, min_score)
        return [SearchResultDTO(**r) for r in results]

    @staticmethod
    async def delete_document(title: str) -> int:
        """删除文档"""
        return await retriever.delete_document(title)

    @staticmethod
    def get_stats() -> dict:
        """获取统计"""
        return retriever.get_stats()
