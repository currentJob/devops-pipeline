"""워커의 Claude tool use 정의 + 안전 가드.

권한 모델 (사이클7 / 권한 그룹 B):
- read_file:   /workspace 하위 모든 파일 (읽기 전용)
- write_file:  /workspace/prompts/output/ 하위만
- bash:        화이트리스트 prefix 매칭 + 셸 메타문자 차단

모든 도구는 path traversal, command injection 방어를 포함한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
from pathlib import Path

from app import config, notion_client

logger = logging.getLogger(__name__)

WORKSPACE = Path("/workspace")
WRITE_PREFIX = "prompts/output/"
MAX_FILE_BYTES = 1_000_000  # 1 MB
BASH_TIMEOUT_S = 30
SHELL_METAS = re.compile(r"[;&|`<>$]")

BASH_ALLOWLIST: tuple[str, ...] = (
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "git status",
    "git diff",
    "git log",
    "git ls-files",
    "git show",
    "uv run pytest",
    "uv run ruff",
    "uv run pip-audit",
    "docker compose ps",
    "docker compose logs",
)


# ── Anthropic tool 정의 (input_schema 는 JSON Schema) ────────────────────────

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


# ── 안전 가드 ────────────────────────────────────────────────────────────────


def _safe_path(rel: str) -> Path:
    if rel.startswith("/"):
        raise ValueError(f"absolute path 거부: {rel}")
    if ".." in rel.replace("\\", "/").split("/"):
        raise ValueError(f"path traversal 거부: {rel}")
    p = (WORKSPACE / rel).resolve()
    if not str(p).startswith(str(WORKSPACE)):
        raise ValueError(f"workspace 이탈: {rel}")
    return p


# ── 도구 구현 ────────────────────────────────────────────────────────────────


def read_file(path: str) -> str:
    try:
        p = _safe_path(path)
    except ValueError as e:
        return f"거부: {e}"
    if not p.is_file():
        return f"파일 없음: {path}"
    size = p.stat().st_size
    if size > MAX_FILE_BYTES:
        return f"파일 너무 큼: {size} bytes (한도 {MAX_FILE_BYTES})"
    return p.read_text(encoding="utf-8", errors="replace")


def write_file(path: str, content: str) -> str:
    if not path.startswith(WRITE_PREFIX):
        return f"쓰기 거부: '{WRITE_PREFIX}' 로 시작해야 함 (받은: {path!r})"
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        return f"콘텐츠 너무 큼: 한도 {MAX_FILE_BYTES} bytes"
    try:
        p = _safe_path(path)
    except ValueError as e:
        return f"거부: {e}"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"저장 완료: {path} ({len(content)} chars)"


def _is_allowed_command(command: str) -> bool:
    cmd = command.strip()
    for prefix in BASH_ALLOWLIST:
        if cmd == prefix or cmd.startswith(prefix + " "):
            return True
    return False


async def bash(command: str) -> str:
    if SHELL_METAS.search(command):
        return "실행 거부: 셸 메타문자(;&|`<>$) 포함"
    if not _is_allowed_command(command):
        return f"실행 거부: allowlist 에 없음. 허용 prefix: {', '.join(BASH_ALLOWLIST)}"

    try:
        args = shlex.split(command)
    except ValueError as e:
        return f"명령 파싱 실패: {e}"

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(WORKSPACE),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=BASH_TIMEOUT_S)
    except TimeoutError:
        return f"실행 타임아웃 {BASH_TIMEOUT_S}s"
    except FileNotFoundError as e:
        return f"명령 실행 실패: {e}"

    out = stdout.decode("utf-8", errors="replace")
    if len(out) > MAX_FILE_BYTES:
        out = out[:MAX_FILE_BYTES] + "\n...(잘림)"
    return f"exit={proc.returncode}\n{out}"


# ── 디스패치 ─────────────────────────────────────────────────────────────────


async def _notion_search(query: str, limit: int = 10) -> str:
    if not config.NOTION_TOKEN:
        return "거부: NOTION_TOKEN 미설정"
    try:
        pages = await notion_client.search_pages(config.NOTION_TOKEN, query, limit)
    except RuntimeError as e:
        return f"Notion 검색 실패: {e}"
    return json.dumps(pages, ensure_ascii=False)


async def _notion_create_page(title: str, content: str, icon: str | None = None) -> str:
    if not config.NOTION_TOKEN:
        return "거부: NOTION_TOKEN 미설정"
    if not config.NOTION_PARENT_PAGE_ID:
        return "거부: NOTION_PARENT_PAGE_ID 미설정"
    result = await notion_client.create_page(
        config.NOTION_TOKEN,
        config.NOTION_PARENT_PAGE_ID,
        title,
        content,
        icon,
    )
    return json.dumps(result, ensure_ascii=False)


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
