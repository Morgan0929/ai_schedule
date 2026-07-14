"""
Agent Middleware — Java Filter/Interceptor 风格的分层拦截

Middleware 层:
  Input    → PII Detection / File Parser / User Context
  Agent    → Tool Call Limit / Summarization / Todo Extraction
  Tool     → Tool Retry / Model Retry
  Output   → Safety Check / Logging / LangSmith Trace
"""
