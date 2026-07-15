"""
Memory System — 三层记忆架构

Working  (Redis)      : 当前对话状态, 会话结束即清除
Short-term (PG)       : 7天摘要 conversation_summary
Long-term  (PG)       : 用户画像 user_profile + user_memory
Vector    (Qdrant)    : 语义记忆 (未来)
"""