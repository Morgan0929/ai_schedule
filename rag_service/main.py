"""
rag-service 入口 — RAG 知识库 (Qdrant + BGE-M3)
端口 8004
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from common.config import settings
from common.exceptions import AppException
from common.models.response import Result


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="AI Schedule Agent — RAG Service",
    version="0.1.0",
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


@app.get("/health", response_model=Result)
async def health_check():
    return Result.success({"status": "ok", "service": "rag-service"})


# ============ 知识库 API ============
@app.post("/api/v1/rag/documents")
async def upload_document(file: UploadFile = File(...)):
    """上传文档到知识库"""
    # TODO: 解析文档 → 分段 → 嵌入 → 存入 Qdrant
    return Result.success({"filename": file.filename, "status": "已接收，处理中"})


@app.get("/api/v1/rag/search")
async def search_knowledge(q: str = Query(..., description="搜索关键词")):
    """搜索知识库"""
    # TODO: 查询嵌入 → Qdrant 检索 → 返回相关文档
    return Result.success({"query": q, "results": []})


@app.get("/api/v1/rag/documents")
async def list_documents():
    """列出知识库文档"""
    return Result.success({"documents": []})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.RAG_SERVICE_PORT,
        reload=settings.ENV == "dev",
    )
