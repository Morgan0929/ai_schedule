"""
rag_service 入口 — RAG 知识库 (Qdrant / In-Memory)
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
from common.models.response import Result

from rag_service.models import DocumentUploadRequest, DocumentSearchRequest
from rag_service.service.rag_service import RagService

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
    allow_origins=["*"],
    allow_credentials=True,
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
    return Result.success({
        "status": "ok",
        "service": "rag-service",
        "stats": RagService.get_stats(),
    })


# ============ 知识库 API ============
@app.post("/api/v1/rag/documents", response_model=Result)
async def upload_document(request: DocumentUploadRequest):
    """上传文档到知识库（文本内容）"""
    result = await RagService.upload_document(request)
    return Result.created(result.model_dump())


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
