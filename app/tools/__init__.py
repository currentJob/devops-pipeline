from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.tools.filesystem import read_file, write_file
from app.tools.obsidian import vault_save, vault_search
from app.tools.research import recent_research
from app.tools.shell import bash

logger = logging.getLogger(__name__)

# 새 도구 추가 시 이 dict 에만 항목 추가 — execute() 수정 불필요 (OCP)
_TOOL_HANDLERS: dict[str, Callable] = {
    "read_file": lambda a: read_file(a["path"]),
    "write_file": lambda a: write_file(a["path"], a["content"]),
    "bash": lambda a: bash(a["command"]),
    "recent_research": lambda a: recent_research(a["topic"]),
    "vault_search": lambda a: vault_search(a["query"], int(a.get("limit", 10)), a.get("tags", "")),
    "vault_save": lambda a: vault_save(
        a["title"],
        a["content"],
        a.get("category", ""),
        a.get("tags", ""),
        a.get("aliases", ""),
    ),
}

# 코루틴(async) 도구 — 나머지(파일 I/O·Qdrant 임베딩)는 블로킹 동기 함수다.
# 새 async 도구 추가 시 여기에 등록할 것 (execute 의 디스패치가 이 집합으로 분기).
_ASYNC_TOOLS: frozenset[str] = frozenset({"bash", "recent_research"})

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
        "name": "recent_research",
        "description": (
            "최신 자료 조사 — Reddit·Hacker News 등에서 최근 한 달 게시물/반응을 수집한다. "
            "'최신 트렌드'·'요즘'·'최근 동향'·채택률 등 시점에 민감하거나 학습 지식으로 "
            "답하기 어려운 주제에만 사용. 출력의 출처 URL 을 근거로 인용할 것."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "조사할 주제"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "vault_search",
        "description": (
            "Obsidian vault 의 기존 노트를 query 로 의미 검색 (미가용 시 키워드 폴백). "
            "매칭 노트의 경로+요약 목록을 반환. /stack 등에서 중복 회피용. "
            "tags 지정 시 해당 계층 태그를 가진 노트로 한정 검색."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "tags": {
                    "type": "string",
                    "description": "계층 태그로 검색 범위 한정 (쉼표 구분, 선택). 예: area/devops, tech/qdrant",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "vault_save",
        "description": (
            "Obsidian vault 에 마크다운 노트(.md)를 저장. "
            "YAML 프론트매터(title/aliases/created/updated/tags/source)를 자동 추가하고 저장 경로를 반환. "
            "content 본문은 Obsidian 양식을 따른다: 맨 위 `> [!summary] TL;DR` 콜아웃, "
            "`##` 제목 구조, 강조는 `> [!tip]`·주의는 `> [!warning]` 콜아웃, "
            "관련 기존 노트는 `[[노트제목]]` 위키링크, 후속 작업은 `- [ ]` 체크박스, 출처는 `[제목](url)`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string", "description": "Obsidian 마크다운 본문"},
                "category": {"type": "string", "description": "분류 폴더명 (선택)"},
                "tags": {
                    "type": "string",
                    "description": (
                        "계층형 중첩 태그를 쉼표로 구분 (선택). "
                        "예: type/research, area/vector-db, tech/qdrant"
                    ),
                },
                "aliases": {
                    "type": "string",
                    "description": "동의어·약어를 쉼표로 구분 (선택). 예: 벡터DB, VectorDB",
                },
            },
            "required": ["title", "content"],
        },
    },
]


# Anthropic Messages API 의 tools= 형식 (= TOOLS_SCHEMA 그대로)
ANTHROPIC_TOOLS = TOOLS_SCHEMA

# 라우트별 허용 도구 — graph._AGENT_CONFIG 와 일치. (general/doc 은 전체)
_ALL_TOOL_NAMES = [s["name"] for s in TOOLS_SCHEMA]
ROUTE_TOOLS: dict[str, list[str]] = {
    "code": ["bash", "read_file", "write_file"],
    "doc": ["read_file", "write_file", "recent_research", "vault_search", "vault_save"],
    "infra": ["bash", "read_file", "write_file"],
    "stack": ["recent_research", "vault_search", "vault_save"],
    "general": _ALL_TOOL_NAMES,
}


def _openai_tool(schema: dict) -> dict:
    """Anthropic 도구 스키마 → OpenAI function-calling 형식."""
    return {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema["description"],
            "parameters": schema["input_schema"],
        },
    }


def openai_tools(schemas: list[dict] | None = None) -> list[dict]:
    """OpenAI(vLLM) tools= 형식 목록. schemas 미지정 시 전체."""
    return [_openai_tool(s) for s in (schemas if schemas is not None else TOOLS_SCHEMA)]


def tools_for(route: str | None) -> tuple[list[dict], list[dict]]:
    """라우트별 (anthropic_schema, openai_schema) 부분집합. 미지정/미지원 라우트는 전체."""
    names = ROUTE_TOOLS.get(route or "", _ALL_TOOL_NAMES)
    anthropic = [s for s in TOOLS_SCHEMA if s["name"] in names]
    return anthropic, openai_tools(anthropic)


# 도구 결과를 잘라 tool-use 루프의 컨텍스트 누적 폭증 억제 (작은 컨텍스트 모델 보호)
_TOOL_RESULT_MAX_CHARS = 4000


def _trim(result: str) -> str:
    if len(result) <= _TOOL_RESULT_MAX_CHARS:
        return result
    return result[:_TOOL_RESULT_MAX_CHARS] + f"\n...(잘림: 총 {len(result)}자)"


async def execute(name: str, args: dict) -> str:
    """도구 이름 + 인자 → 결과 문자열 (4000자 초과 시 트림)."""
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return f"알 수 없는 도구: {name}"
    try:
        if name in _ASYNC_TOOLS:
            result = await handler(args)
        else:
            # 동기 도구(파일 I/O·Qdrant 임베딩 검색/저장)는 블로킹이므로 스레드로
            # 오프로드해 이벤트 루프(동시 실행 중인 다른 작업)를 막지 않는다.
            result = await asyncio.to_thread(handler, args)
        return _trim(result)
    except KeyError as e:
        return f"필수 인자 누락: {e}"
    except Exception as e:
        logger.exception("도구 실행 오류 name=%s", name)
        return f"도구 실행 오류: {e}"
