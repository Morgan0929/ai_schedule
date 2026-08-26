"""
Document Analyzer Tool — 文档图像分析

林的秘书能力扩展: 识别课程表、作业、通知、票据等文档图片

架构:
  林 Agent → analyze_document 工具 → VisionService → DeepSeek VL
                                                    ↓ (换模型只改这里)
                                               Qwen VL / GPT-4V

返回结构化数据 → Calendar / Task / Reminder 工具进一步处理
"""
import base64
import logging
from typing import Any
from common.utils.llm_guard import guarded_llm_call

logger = logging.getLogger(__name__)


def _extract_json(content: str) -> dict | None:
    """从 LLM 回复中提取 JSON"""
    import json
    # markdown code block
    for marker in ["```json", "```"]:
        if marker in content:
            try:
                start = content.index(marker) + len(marker)
                end = content.index("```", start)
                return json.loads(content[start:end].strip())
            except (ValueError, json.JSONDecodeError):
                continue
    # brace extraction
    try:
        brace_start = content.index("{")
        brace_end = content.rindex("}") + 1
        return json.loads(content[brace_start:brace_end])
    except (ValueError, json.JSONDecodeError):
        return None

# 支持的文档类型 & 提取 Schema
DOC_SCHEMAS = {
    "course_schedule": {
        "label": "课程表",
        "fields": ["课程名称", "教师", "教室", "星期(1-7)", "开始节次", "结束节次", "周次(如1-16)"],
        "follow_up": "create_task",  # 识别后建议创建任务
    },
    "homework": {
        "label": "作业",
        "fields": ["科目", "内容", "截止时间", "提交方式"],
        "follow_up": "create_task",
    },
    "exam_notice": {
        "label": "考试通知",
        "fields": ["科目", "考试时间", "地点", "座位号", "注意事项"],
        "follow_up": "set_reminder",
    },
    "meeting_notice": {
        "label": "会议通知",
        "fields": ["会议主题", "时间", "地点", "组织者", "参与人"],
        "follow_up": "create_task",
    },
    "ticket": {
        "label": "票据(车票/机票/电影票)",
        "fields": ["类型", "出发地", "目的地", "出发时间", "到达时间", "座位号"],
        "follow_up": "create_task",
    },
    "announcement": {
        "label": "通知公告",
        "fields": ["标题", "发布单位", "主要内容", "生效日期", "截止日期"],
        "follow_up": None,
    },
    "generic": {
        "label": "通用文档",
        "fields": ["主要内容", "关键日期", "行动项"],
        "follow_up": None,
    },
}


class DocumentAnalyzer:
    """
    文档分析器 — 林的"眼睛"

    使用:
      result = await DocumentAnalyzer.analyze(
          image_base64="...",
          doc_type="course_schedule",
          hint="这是大二下学期的课表"
      )
    """

    @staticmethod
    async def analyze(
        image_base64: str,
        doc_type: str = "generic",
        hint: str = "",
    ) -> dict:
        """
        分析文档图片，返回结构化信息

        Args:
            image_base64: 图片 base64
            doc_type:     文档类型 (course_schedule/homework/exam_notice/...)
            hint:         额外提示 ("这是大二课表", "截图中第3行是重点")

        Returns:
            {
                "type": "course_schedule",
                "items": [{"课程名称": "高数", ...}],
                "summary": "...",
                "suggested_action": "create_task" | "set_reminder" | null
            }
        """
        schema = DOC_SCHEMAS.get(doc_type, DOC_SCHEMAS["generic"])

        system = (
            f"你是林的文档识别引擎。分析这张{schema['label']}图片，提取结构化信息。\n\n"
            f"提取字段: {', '.join(schema['fields'])}\n"
            f"提示: {hint}\n\n"
            f"严格返回 JSON (不要其他内容):\n"
            f'{{"type": "{doc_type}", '
            f'"items": [{{"字段1": "值1", ...}}], '
            f'"summary": "一句话总结", '
            f'"suggested_action": "{schema["follow_up"] or "none"}"}}'
        )

        from agent_service.llm.deepseek_client import is_llm_available, get_structured_llm
        from agent_service.llm.prompts import vision_system_template
        from agent_service.graph.schemas import VisionOutput

        if not is_llm_available():
            return {"type": doc_type, "items": [], "mock": True,
                    "summary": "Document Analyzer 需要 DeepSeek API Key"}

        try:
            system_content = vision_system_template.format(
                doc_type_label=schema["label"],
                doc_fields=", ".join(schema["fields"]),
                hint=hint,
                doc_type=doc_type,
                suggested_action=schema["follow_up"] or "none",
            )

            # LangChain 暂不支持多模态 structured output,
            # 用原生 API + Pydantic model_validate
            from agent_service.llm.deepseek_client import get_llm_client
            from common.config import Settings
            client = get_llm_client()
            if not client:
                return {"type": doc_type, "items": [], "mock": True, "summary": "API 不可用"}

            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": [
                    {"type": "text", "text": "请分析这张文档图片"},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }},
                ]},
            ]

            resp = await guarded_llm_call(
                "vision",
                lambda: client.chat.completions.create(
                    model=Settings().DEEPSEEK_MODEL, messages=messages,
                    temperature=0.3, max_tokens=2048,
                    response_format={"type": "json_object"},
                ),
                timeout=30.0,
            )
            raw = resp.choices[0].message.content.strip()

            import json
            try:
                data = json.loads(raw)
                # Pydantic 校验
                result = VisionOutput(**data)
                logger.info(f"DocumentAnalyzer: {result.document_type} confidence={result.confidence}")
                return result.model_dump()
            except Exception:
                pass
            return {"type": doc_type, "items": [], "raw_text": raw[:500]}

        except Exception as e:
            logger.error(f"DocumentAnalyzer error: {e}")
            return {"type": doc_type, "items": [], "error": str(e)}

    # ========== 便捷方法 ==========

    @staticmethod
    def image_to_base64(filepath: str) -> str | None:
        """本地文件 → base64"""
        try:
            with open(filepath, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to load: {e}")
            return None

    @staticmethod
    def bytes_to_base64(data: bytes) -> str:
        """bytes → base64"""
        return base64.b64encode(data).decode("utf-8")

    @staticmethod
    def guess_doc_type(hint: str) -> str:
        """根据用户提示猜测文档类型"""
        keywords = {
            "course_schedule": ["课表", "课程", "上课", "选课"],
            "homework": ["作业", "题目", "习题", "报告"],
            "exam_notice": ["考试", "考场", "准考证"],
            "meeting_notice": ["会议", "开会", "周会"],
            "ticket": ["票", "车票", "机票", "电影票", "火车票"],
            "announcement": ["通知", "公告", "公示"],
        }
        for doc_type, kws in keywords.items():
            if any(kw in hint for kw in kws):
                return doc_type
        return "generic"
