from __future__ import annotations

import logging

from app.tools.filesystem import MAX_FILE_BYTES, WORKSPACE, WRITE_PREFIX, read_file, write_file
from app.tools.notion import _notion_create_page, _notion_search
from app.tools.shell import BASH_ALLOWLIST, BASH_TIMEOUT_S, SHELL_METAS, bash

logger = logging.getLogger(__name__)

TOOLS_SCHEMA = [
    {
        "name": "read_file",
        "description": (
            "프로젝트 워크스페이스의 파일을 읽는다. "
            "경로는 프로젝트 루트 기준 상대 경로 (예: 'app/main.py'). "
            "1MB 초과 파일은 거부."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "프로젝트 루트 기준 상대 경로"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "prompts/output/ 하위에만 파일을 쓴다. 다른 경로는 거부된다. "
            "워크플로 분석 보고서/리서치 결과 등을 저장하는 용도."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "prompts/output/ 으로 시작하는 상대 경로",
                },
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "bash",
        "description": (
            "허용된 명령만 실행한다 (ls, cat, git status/diff/log, "
            "uv run pytest/ruff/pip-audit, docker compose ps/logs). "
            "셸 메타문자(;&|`<>$) 사용 시 거부. 30초 타임아웃."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "notion_search",
        "description": (
            "Notion 워크스페이스 내 페이지 검색. query 키워드로 매칭되는 페이지의 "
            "id, title, url 리스트(JSON 문자열)를 반환. /stack 워크플로에서 중복 회피용."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "notion_create_page",
        "description": (
            "NOTION_PARENT_PAGE_ID 하위에 새 페이지를 생성. "
            "title 과 마크다운 본문(content), 선택적 emoji icon 을 받아 "
            "{id, url} 또는 {error} 를 JSON 문자열로 반환. "
            "마크다운은 자동으로 Notion 블록으로 변환됨 (헤딩/리스트/코드/단락 지원)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string", "description": "마크다운 본문"},
                "icon": {"type": "string", "description": "이모지 1자 (선택)"},
            },
            "required": ["title", "content"],
        },
    },
]


async def execute(name: str, args: dict) -> str:
    """Claude 가 호출한 도구 이름 + 인자 → 결과 문자열."""
    try:
        if name == "read_file":
            return read_file(args["path"])
        if name == "write_file":
            return write_file(args["path"], args["content"])
        if name == "bash":
            return await bash(args["command"])
        if name == "notion_search":
            return await _notion_search(args["query"], int(args.get("limit", 10)))
        if name == "notion_create_page":
            return await _notion_create_page(args["title"], args["content"], args.get("icon"))
    except KeyError as e:
        return f"필수 인자 누락: {e}"
    except Exception as e:
        logger.exception("도구 실행 오류 name=%s", name)
        return f"도구 실행 오류: {e}"
    return f"알 수 없는 도구: {name}"
