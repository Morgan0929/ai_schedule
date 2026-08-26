"""
rag_service — PostgreSQL + pgvector RAG 知识库
端口 8004
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.config import settings
from common.exceptions import AppException
from common.schemas.response import Result

from rag_service.models.rag_model import DocumentUploadRequest, DocumentSearchRequest
from rag_service.services.rag_service import RagService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"RAG service started (embedding dim: {RagService.get_stats()})")
    yield


app = FastAPI(
    title="AI Schedule Agent — RAG Service",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.code,
        content=Result.error(exc.code, exc.message).model_dump(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content=Result.error(500, str(exc)).model_dump(),
    )


@app.get("/health", response_model=Result)
async def health_check():
    return Result.success({"status": "ok", "service": "rag-service"})


# ============ Document RAG API ============
@app.post("/api/v1/rag/documents", response_model=Result)
async def upload_document(request: DocumentUploadRequest):
    """上传文档 → 分段 → embedding → pgvector"""
    result = await RagService.upload_document(
        user_id=1,  # TODO: JWT
        filename=request.title,
        content=request.content,
        file_type=request.doc_type,
    )
    return Result.created(result)


@app.get("/api/v1/rag/search", response_model=Result)
async def search_documents(
    q: str = Query(..., description="搜索查询"),
    top_k: int = Query(5, ge=1, le=20),
    category: str = Query(None, description="按分类过滤 (course/project等)"),
):
    """文档语义搜索 (pgvector cosine similarity)"""
    results = await RagService.search_documents(user_id=1, query=q, top_k=top_k, category=category)
    return Result.success(results)


# ============ Memory RAG API ============
@app.post("/api/v1/rag/memory", response_model=Result)
async def save_memory(request: dict):
    """保存语义记忆 (从对话中提取的习惯/偏好/事实)"""
    result = await RagService.save_semantic_memory(
        user_id=request.get("user_id", 1),
        content=request["content"],
        memory_type=request.get("memory_type", "general"),
        confidence=request.get("confidence", 0.5),
    )
    return Result.created(result)


@app.get("/api/v1/rag/memory/search", response_model=Result)
async def search_memory(
    q: str = Query(...),
    memory_type: str = Query(None),
    top_k: int = Query(5),
):
    """语义记忆搜索 — '之前那个旅游计划怎么样了?'"""
    results = await RagService.search_semantic_memory(
        user_id=1, query=q, memory_type=memory_type, top_k=top_k,
    )
    return Result.success(results)


@app.post("/api/v1/rag/memory/cleanup", response_model=Result)
async def cleanup_memories(user_id: int = Query(1), min_confidence: float = Query(0.3)):
    """清理低置信度记忆"""
    count = await RagService.cleanup_memories(user_id, min_confidence)
    return Result.success({"deleted": count})


@app.get("/api/v1/rag/search", response_model=Result)
async def search_knowledge(
    q: str = Query(..., description="搜索查询"),
    top_k: int = Query(5, ge=1, le=20),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
):
    """搜索知识库"""
    results = await RagService.search(q, top_k, min_score)
    return Result.success([r.model_dump() for r in results])


@app.get("/api/v1/rag/documents", response_model=Result)
async def get_stats():
    """获取知识库统计"""
    return Result.success(RagService.get_stats())


@app.delete("/api/v1/rag/documents/{title}", response_model=Result)
async def delete_document(title: str):
    """删除文档"""
    count = await RagService.delete_document(title)
    return Result.success({"title": title, "deleted_chunks": count})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.RAG_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
