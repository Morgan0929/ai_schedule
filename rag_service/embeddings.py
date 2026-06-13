"""
BGE-M3 嵌入模型

将文本转换为向量，用于 Qdrant 检索
"""
from typing import Any


class EmbeddingService:
    """
    嵌入服务

    使用 BGE-M3 模型将文本转为向量
    BGE-M3 特点：
    - 支持多语言（中英）
    - 支持 dense + sparse 混合检索
    - 向量维度 1024
    """

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model_name = model_name
        self.model = None  # 延迟加载

    async def initialize(self):
        """加载模型（首次使用时）"""
        # TODO: 使用 sentence-transformers 加载
        # from sentence_transformers import SentenceTransformer
        # self.model = SentenceTransformer(self.model_name)
        pass

    async def encode(self, texts: list[str]) -> list[list[float]]:
        """
        将文本列表转为向量列表

        Args:
            texts: 待编码文本

        Returns:
            向量列表，每个向量 1024 维
        """
        # TODO: 调用模型编码
        # if self.model is None:
        #     await self.initialize()
        # embeddings = self.model.encode(texts, normalize_embeddings=True)
        # return embeddings.tolist()
        return [[0.0] * 1024] * len(texts)

    async def encode_single(self, text: str) -> list[float]:
        """编码单个文本"""
        results = await self.encode([text])
        return results[0]


# 全局单例
embedding_service = EmbeddingService()
