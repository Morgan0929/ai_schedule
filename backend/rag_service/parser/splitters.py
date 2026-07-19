"""
Document Splitters — 每种文档类型独立的切分策略

原则:
  - 课程表  → 不切, 结构化提取
  - 作业通知 → 不切, 提取为事件
  - 会议纪要 → 按标题/章节切
  - 通用文档 → RecursiveCharacterTextSplitter
"""
import re
from rag_service.parser.classifier import DocumentType


class BaseSplitter:
    """Splitter 基类"""

    async def split(self, text: str, metadata: dict = None) -> list[dict]:
        """返回 [{"content": "...", "metadata": {...}}, ...]"""
        raise NotImplementedError


class RecursiveSplitter(BaseSplitter):
    """通用文档: RecursiveCharacterTextSplitter (chunk=800, overlap=150)"""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def split(self, text: str, metadata: dict = None) -> list[dict]:
        # 先用 natural separators 切
        separators = ["\n\n", "\n", "。", "！", "？", ". ", "! ", "? ", " "]
        return _split_with_overlap(text, self.chunk_size, self.chunk_overlap,
                                    separators, metadata or {})


class MeetingSplitter(BaseSplitter):
    """会议纪要: 按标题/章节切 (不按字符数)"""

    async def split(self, text: str, metadata: dict = None) -> list[dict]:
        meta = metadata or {}
        # 按 # / ## / ### 标题切分
        sections = re.split(r"\n(?=#{1,3}\s)", text)

        chunks = []
        for section in sections:
            section = section.strip()
            if not section:
                continue

            # 提取标题
            title_match = re.match(r"#{1,3}\s(.+)", section)
            title = title_match.group(1) if title_match else ""

            # 标记 section 类型
            section_type = "general"
            lower = section.lower()
            if any(kw in lower for kw in ["决定", "决议", "结论"]):
                section_type = "decision"
            elif any(kw in lower for kw in ["todo", "待办", "行动"]):
                section_type = "todo"
            elif any(kw in lower for kw in ["讨论", "议题"]):
                section_type = "discussion"

            chunks.append({
                "content": section,
                "metadata": {**meta, "section_title": title, "section_type": section_type},
            })

        return chunks


class CourseExtractor(BaseSplitter):
    """课程表: 不切 → 结构化提取, 送入 SQL + RAG"""

    async def split(self, text: str, metadata: dict = None) -> list[dict]:
        """返回结构化课程数据, 不产生常规 chunk"""
        meta = metadata or {}
        chunks = []

        # 尝试解析每一行
        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) < 5:
                continue

            course = _extract_course_line(line)
            if course:
                course["_extracted"] = True
                course["_type"] = "course"
                chunks.append({
                    "content": json.dumps(course, ensure_ascii=False),
                    "metadata": {**meta, "category": "course", "structured": True,
                                 **{f"course_{k}": v for k, v in course.items()}},
                })

        return chunks if chunks else [{"content": text, "metadata": meta}]  # 解析失败则作为普通文本


class AssignmentExtractor(BaseSplitter):
    """作业通知: 不切 → 提取为事件"""

    async def split(self, text: str, metadata: dict = None) -> list[dict]:
        meta = metadata or {}
        extracted = _extract_assignment(text)

        if extracted:
            import json
            return [{
                "content": json.dumps(extracted, ensure_ascii=False),
                "metadata": {**meta, "category": "assignment", "structured": True,
                             **{f"assignment_{k}": v for k, v in extracted.items()}},
            }]
        return [{"content": text, "metadata": meta}]


class NoSplitter(BaseSplitter):
    """不切 — 整个文档作为一个 chunk (适用于票据等短文档)"""

    async def split(self, text: str, metadata: dict = None) -> list[dict]:
        return [{"content": text, "metadata": metadata or {}}]


# ========== Splitter Registry ==========

SPLITTER_REGISTRY: dict[DocumentType, BaseSplitter] = {
    DocumentType.COURSE: CourseExtractor(),
    DocumentType.ASSIGNMENT: AssignmentExtractor(),
    DocumentType.MEETING: MeetingSplitter(),
    DocumentType.TICKET: NoSplitter(),
    DocumentType.PROJECT: RecursiveSplitter(chunk_size=1000, chunk_overlap=200),
    DocumentType.REPORT: RecursiveSplitter(chunk_size=800, chunk_overlap=150),
    DocumentType.EMAIL: MeetingSplitter(),  # 按标题切
    DocumentType.GENERAL: RecursiveSplitter(chunk_size=800, chunk_overlap=150),
}


def get_splitter(doc_type: DocumentType) -> BaseSplitter:
    return SPLITTER_REGISTRY.get(doc_type, RecursiveSplitter())


# ========== Helpers ==========

import json


def _split_with_overlap(text: str, chunk_size: int, overlap: int,
                        separators: list[str], metadata: dict) -> list[dict]:
    """简单 sliding window 切分"""
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        raw = text[start:end]

        # 尝试在 separator 处断开
        best_end = end
        for sep in separators:
            pos = raw.rfind(sep, max(0, len(raw) - 100))
            if pos > chunk_size // 2:
                best_end = start + pos + len(sep)
                break

        chunk_text = text[start:best_end].strip()
        if chunk_text:
            chunks.append({"content": chunk_text, "metadata": {**metadata, "chunk_index": idx}})
            idx += 1

        start = best_end - overlap if best_end < end else end - overlap
        if start <= 0:
            start = end - overlap if end > overlap else end

    return chunks


def _extract_course_line(line: str) -> dict | None:
    """从一行文本中提取课程信息"""
    patterns = [
        # "周一 1-2节 高等数学 A301 张教授"
        r"(周[一二三四五六日])\s*(\d{1,2})[-\s]*(\d{1,2})节\s*(.{2,20}?)\s*([A-Za-z0-9\-]+)\s*(.{0,10})",
        # "数据结构 周一 09:00-10:40 教1-301"
        r"(.{2,20}?)\s*周([一二三四五六日])\s*(\d{1,2}):(\d{2})\s*[-~]\s*(\d{1,2}):(\d{2})\s*(.{0,20})",
    ]

    for pat in patterns:
        m = re.search(pat, line)
        if m:
            groups = m.groups()
            if "节" in pat:
                return {
                    "day": groups[0], "start": int(groups[1]),
                    "end": int(groups[2]), "course": groups[3].strip(),
                    "location": groups[4].strip(), "teacher": groups[5].strip() if len(groups) > 5 else "",
                }
            else:
                return {
                    "course": groups[0].strip(), "day": f"周{groups[1]}",
                    "start_time": f"{groups[2]}:{groups[3]}",
                    "end_time": f"{groups[4]}:{groups[5]}",
                    "location": groups[6].strip() if len(groups) > 6 else "",
                }
    return None


def _extract_assignment(text: str) -> dict | None:
    """从作业通知中提取关键信息"""
    info = {"title": "", "deadline": "", "course": "", "format": ""}

    # 提取课程名
    course_match = re.search(r"(《.+?》|Java|Python|数学|英语|物理|数据结构|操作系统)", text)
    if course_match:
        info["course"] = course_match.group(1)

    # 提取截止时间
    deadline_patterns = [
        r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        r"(\d{1,2}月\d{1,2}日)",
        r"(截止|deadline|due)[:：\s]*(\S+)",
    ]
    for pat in deadline_patterns:
        m = re.search(pat, text, re.I)
        if m:
            info["deadline"] = m.group(1) if m.lastindex == 1 else m.group(2)
            break

    # 提取标题
    title_match = re.search(r"(提交|完成|撰写|编写)(.{2,30}?)(?:，|。|$|截止|之前)", text)
    if title_match:
        info["title"] = (title_match.group(1) + title_match.group(2)).strip()

    return info if any(info.values()) else None
