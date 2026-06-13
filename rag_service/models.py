"""
RAG 服务 — 数据模型
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class DocumentUploadRequest(BaseModel):
    """文档上传请求"""
    title: str = Field(..., min_length=1, max_length=256)
    content: str = Field(..., min_length=1)
    doc_type: str = Field(default="GENERAL", description="文档类型: POLICY/GUIDE/FAQ/GENERAL")
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentSearchRequest(BaseModel):
    """文档搜索请求"""
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class DocumentDTO(BaseModel):
    """文档响应"""
    title: str
    chunks: int
    chunk_ids: list[str] = []


class SearchResultDTO(BaseModel):
    """搜索结果"""
    id: str
    score: float
    title: str
    content: str
    doc_type: str = ""
    chunk_index: int = 0
