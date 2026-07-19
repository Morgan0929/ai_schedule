"""
Document Classifier — 识别文档类型, 决定后续处理策略

分类优先: 先判断类型 → 再选择 Splitter/Extractor
"""
from enum import Enum
from dataclasses import dataclass, field


class DocumentType(str, Enum):
    COURSE = "course"           # 课程表
    ASSIGNMENT = "assignment"   # 作业通知
    MEETING = "meeting"         # 会议纪要
    PROJECT = "project"         # 项目文档
    REPORT = "report"           # 报告/论文
    EMAIL = "email"             # 邮件
    TICKET = "ticket"           # 票据(车票/机票)
    GENERAL = "general"         # 通用文档


@dataclass
class ClassificationResult:
    """文档分类结果"""
    doc_type: DocumentType
    confidence: float
    extracted_metadata: dict = field(default_factory=dict)
    structured_data: list[dict] = field(default_factory=list)
    needs_chunking: bool = True   # False = 结构化提取后不需要chunk


# 关键词分类规则
TYPE_KEYWORDS: dict[DocumentType, list[str]] = {
    DocumentType.COURSE: [
        "课程表", "课表", "上课", "课程", "选修", "必修", "学分",
        "周一", "周二", "周三", "周四", "周五", "节次", "教室", "教师",
        "schedule", "course", "class",
    ],
    DocumentType.ASSIGNMENT: [
        "作业", "提交", "截止", "实验报告", "习题", "论文提交",
        "deadline", "assignment", "homework", "due",
    ],
    DocumentType.MEETING: [
        "会议", "参会", "讨论", "纪要", "议题", "决议", "TODO",
        "meeting", "minutes", "agenda",
    ],
    DocumentType.PROJECT: [
        "项目", "架构", "设计文档", "需求", "模块", "接口",
        "project", "architecture", "design",
    ],
    DocumentType.REPORT: [
        "报告", "总结", "分析", "调研", "综述", "汇报",
        "report", "summary", "analysis",
    ],
    DocumentType.EMAIL: [
        "发件人", "收件人", "主题", "抄送", "邮件",
        "from:", "to:", "subject:", "email",
    ],
    DocumentType.TICKET: [
        "车票", "机票", "电影票", "订单号", "座位", "出发", "到达",
        "ticket", "booking", "flight",
    ],
}


class DocumentClassifier:
    """
    文档分类器 — 关键词 + LLM 双重判定

    Usage:
        result = await DocumentClassifier.classify(text, filename)
        if result.doc_type == DocumentType.COURSE:
            # use CourseExtractor
    """

    @staticmethod
    def classify_by_keywords(text: str, filename: str = "") -> ClassificationResult:
        """
        关键词快速分类 (无需 LLM)
        """
        text_lower = (text + filename).lower()

        best_type = DocumentType.GENERAL
        best_score = 0

        for doc_type, keywords in TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text_lower)
            if score > best_score:
                best_score = score
                best_type = doc_type

        confidence = min(0.9, best_score / 5.0) if best_score > 0 else 0.3

        # 决定是否需要 chunk
        needs_chunking = best_type not in (
            DocumentType.COURSE, DocumentType.ASSIGNMENT,
            DocumentType.TICKET, DocumentType.MEETING,
        )

        return ClassificationResult(
            doc_type=best_type,
            confidence=confidence,
            needs_chunking=needs_chunking,
        )

    @staticmethod
    async def classify(text: str, filename: str = "",
                       use_llm: bool = False) -> ClassificationResult:
        """
        完整分类 (关键词 + 可选 LLM)
        """
        result = DocumentClassifier.classify_by_keywords(text, filename)

        # 低置信度时用 LLM 辅助
        if result.confidence < 0.5 and use_llm:
            llm_result = await _llm_classify(text, filename)
            if llm_result:
                result = llm_result

        return result


async def _llm_classify(text: str, filename: str) -> ClassificationResult | None:
    """LLM 分类 (低置信度时使用)"""
    from agent_service.llm.deepseek_client import is_llm_available, get_structured_llm
    if not is_llm_available():
        return None

    from pydantic import BaseModel

    class LLMClassify(BaseModel):
        doc_type: str
        confidence: float

    prompt = (
        f"判断文档类型: {filename}\n"
        f"内容片段: {text[:1000]}\n"
        f"类型: course/assignment/meeting/project/report/email/ticket/general"
    )
    try:
        llm = get_structured_llm(LLMClassify)
        result = await llm.ainvoke(prompt)
        if hasattr(result, "doc_type"):
            dt = result.doc_type
            for t in DocumentType:
                if t.value == dt:
                    return ClassificationResult(
                        doc_type=t, confidence=result.confidence,
                        needs_chunking=t not in (
                            DocumentType.COURSE, DocumentType.ASSIGNMENT,
                            DocumentType.TICKET, DocumentType.MEETING,
                        ),
                    )
    except Exception:
        pass
    return None
