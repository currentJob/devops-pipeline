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
