"""LangChain @tool 래퍼 — app/tools/ 의 보안 로직을 그대로 재사용."""

from __future__ import annotations

from langchain_core.tools import tool

from app.tools.filesystem import read_file as _read_file
from app.tools.filesystem import write_file as _write_file
from app.tools.notion import _notion_create_page, _notion_search
from app.tools.research import recent_research as _recent_research
from app.tools.shell import bash as _bash

# 도구 결과를 잘라 ReAct 컨텍스트 누적 폭증을 억제 (작은 컨텍스트 모델 보호)
_TOOL_RESULT_MAX_CHARS = 4000


def _trim(result: str) -> str:
    if len(result) <= _TOOL_RESULT_MAX_CHARS:
        return result
    return result[:_TOOL_RESULT_MAX_CHARS] + f"\n...(잘림: 총 {len(result)}자)"


@tool
def read_file(path: str) -> str:
    """프로젝트 워크스페이스 파일 읽기. 경로는 루트 기준 상대 경로 (예: 'app/main.py'). 1MB 초과 거부."""
    return _trim(_read_file(path))


@tool
def write_file(path: str, content: str) -> str:
    """prompts/output/ 하위에만 파일 쓰기. 분석 보고서·리서치 결과 저장용."""
    return _write_file(path, content)


@tool
async def bash(command: str) -> str:
    """허용된 셸 명령 실행 (ls, cat, git status/diff/log, uv run pytest/ruff/pip-audit, docker compose ps/logs). 메타문자(;&|`<>$) 거부. 30초 타임아웃."""
    return _trim(await _bash(command))


@tool
async def recent_research(topic: str) -> str:
    """최신 자료 조사 — Reddit·Hacker News 등에서 최근 한 달 게시물/반응을 수집한다.
    '최신 트렌드', '요즘', '최근 동향', 채택률·평판 등 시점에 민감하거나 학습 지식으로
    답하기 어려운 주제에만 사용하라. 출력의 출처 URL 을 근거로 인용할 것."""
    return await _recent_research(topic)


@tool
async def notion_search(query: str, limit: int = 10) -> str:
    """Notion 워크스페이스 페이지 검색. 중복 회피 및 기존 내용 확인용."""
    return _trim(await _notion_search(query, limit))


@tool
async def notion_create_page(title: str, content: str, icon: str = "📋") -> str:
    """NOTION_PARENT_PAGE_ID 하위에 마크다운 콘텐츠로 새 페이지 생성. 마크다운 자동 변환."""
    return await _notion_create_page(title, content, icon)


TOOLS = [read_file, write_file, bash, recent_research, notion_search, notion_create_page]
