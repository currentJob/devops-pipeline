import os

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"필수 환경변수 누락: {key}")
    return val


TELEGRAM_TOKEN: str = _require("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID: int = int(_require("TELEGRAM_CHAT_ID"))
CLAUDE_API_KEY: str = os.environ.get("CLAUDE_API_KEY", "")
APPROVAL_TIMEOUT: int = int(os.environ.get("APPROVAL_TIMEOUT", "300"))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
# Notion 통합 (선택 — /stack 명령어에서 사용)
NOTION_TOKEN: str = os.environ.get("NOTION_TOKEN", "")
NOTION_PARENT_PAGE_ID: str = os.environ.get("NOTION_PARENT_PAGE_ID", "")
# RAG 웹 검색 (선택 — Brave Search API 키, https://brave.com/search/api/)
BRAVE_API_KEY: str = os.environ.get("BRAVE_API_KEY", "")
# 워커 에이전트 튜닝
WORKER_BOT_NOTIFY_URL: str = os.environ.get("BOT_NOTIFY_URL", "http://bot:8765/notify")
WORKER_BOT_RESULT_URL: str = os.environ.get("BOT_RESULT_URL", "http://bot:8765/worker-result")
WORKER_MODEL: str = os.environ.get("WORKER_MODEL", "claude-sonnet-4-6")
WORKER_MAX_TOKENS: int = int(os.environ.get("WORKER_MAX_TOKENS", "8192"))
WORKER_MAX_ITERATIONS: int = int(os.environ.get("WORKER_MAX_ITERATIONS", "10"))
WORKER_TIMEOUT_S: float = float(os.environ.get("WORKER_TIMEOUT_S", "120"))
WORKER_URL: str = os.environ.get("WORKER_URL", "http://worker:8766/run")
WORKER_HEALTH_URL: str = os.environ.get("WORKER_HEALTH_URL", "http://worker:8766/health")
WORKER_TASKS_URL: str = os.environ.get("WORKER_TASKS_URL", "http://worker:8766/tasks")
WORKER_MAX_CONCURRENT: int = int(os.environ.get("WORKER_MAX_CONCURRENT", "3"))
WORKER_QUEUE_SIZE: int = int(os.environ.get("WORKER_QUEUE_SIZE", "50"))
