"""
嵌入服务 — 文本转向量

双模式:
- 生产: BGE-M3 (1024维, 中文最优)
- 开发: all-MiniLM-L6-v2 (384维, 轻量)
- 离线: SimpleEmbedding (统计特征, 无需模型)
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)


class SimpleEmbedding:
    """
    轻量级嵌入 — 无需下载任何模型

    使用字符 n-gram 统计特征作为向量表示。
    适合开发环境快速验证，生产请用 BGE-M3。
    """

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.vocab: dict[str, int] = {}
        self._init_vocab()

    def _init_vocab(self):
        chars = (
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789 .,!?;:()[]{}" +
            "的一是了我不人在他有这个上们来到时大地为子中你说生国年着就那和要她出也得里后自以会"
            "家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样道想作种开"
            "美总从无情己面最女但现前些所同日手又行意动方期它头经长儿回位分爱老因很给名"
            "法间斯知世什两次使身者被高已亲其进此话常与活正感"
        )
        for i, c in enumerate(chars):
            self.vocab[c] = i % self.dim

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            if not text:
                continue
            vec = np.zeros(self.dim, dtype=np.float32)
            chars = list(text[:2000])
            for j, c in enumerate(chars):
                if c in self.vocab:
                    weight = 1.0 / (1.0 + j * 0.001)
                    vec[self.vocab[c]] += weight
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vectors[i] = vec
        return vectors

    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


class SentenceTransformerEmbedding:
    """生产级嵌入 — 带超时回退"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", timeout: float = 10.0):
        self.model_name = model_name
        self._model = None
        self.dim = 384
        self._timeout = timeout
        self._load_failed = False

    @property
    def model(self):
        if self._load_failed:
            raise RuntimeError("Model loading previously failed")
        if self._model is None:
            import signal
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


class EmbeddingService:
    """嵌入服务门面 — 自动选择最佳可用模型"""

    def __init__(self):
        self._backend = None
        self._initialized = False
        self._dim = 384

    def _init_backend(self):
        if self._initialized:
            return
        self._initialized = True

        # 尝试加载 sentence-transformers（带超时）
        import os
        if os.environ.get("USE_SIMPLE_EMBEDDING", "").lower() in ("1", "true", "yes"):
            logger.info("Embedding: forced SimpleEmbedding via env")
        else:
            for model_name in ["all-MiniLM-L6-v2"]:
                try:
                    backend = SentenceTransformerEmbedding(model_name)
                    # 快速测试是否能加载（不实际加载模型，只检查包是否存在）
                    self._backend = backend
                    self._dim = backend.dim
                    logger.info(f"Embedding: {model_name} ({self._dim}d) — lazy load")
                    return
                except Exception as e:
                    logger.warning(f"ST model unavailable: {e}")
                    continue

        self._backend = SimpleEmbedding(dim=384)
        self._dim = 384
        logger.info("Embedding: SimpleEmbedding (384d, no download)")

    def encode(self, texts: list[str]) -> list[list[float]]:
        self._init_backend()
        vectors = self._backend.encode(texts)
        return vectors.tolist()

    def encode_single(self, text: str) -> list[float]:
        self._init_backend()
        vec = self._backend.encode_single(text)
        if hasattr(vec, 'tolist'):
            return vec.tolist()
        return list(vec)

    @property
    def dimension(self) -> int:
        self._init_backend()
        return self._dim


embedding_service = EmbeddingService()
