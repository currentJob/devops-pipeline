"""Anthropic Agent SDK 도구 정의 — Claude 경로(tool_runner)용 @beta_async_tool 래퍼.

각 래퍼는 스키마(이름·설명·인자)를 시그니처+docstring 으로 선언하고, 실제 실행은
단일 레지스트리 app.tools.execute(권한 가드·트림·스레드 오프로드·오류 처리)에 위임한다.
라우트별 도구 부분집합은 app.tools.ROUTE_TOOLS 를 단일 소스로 재사용한다.

vLLM(openai) 경로는 기존 app.tools 의 openai 스키마를 그대로 쓰므로 여기 대상이 아니다.
"""

from __future__ import annotations

from anthropic import beta_async_tool

from app import tools as _tools


@beta_async_tool
async def read_file(path: str) -> str:
    """프로젝트 워크스페이스의 파일을 읽는다 (루트 기준 상대 경로, 1MB 초과 거부).

    Args:
        path: 프로젝트 루트 기준 상대 경로 (예: app/main.py)
    """
    return await _tools.execute("read_file", {"path": path})


@beta_async_tool
async def write_file(path: str, content: str) -> str:
    """prompts/output/ 하위에만 파일을 쓴다. 다른 경로는 거부된다.

    Args:
        path: prompts/output/ 으로 시작하는 상대 경로
        content: 파일 내용
    """
    return await _tools.execute("write_file", {"path": path, "content": content})


@beta_async_tool
async def bash(command: str) -> str:
    """허용된 명령만 실행한다 (ls, cat, git status/diff/log, uv run pytest/ruff/pip-audit 등).

    셸 메타문자(;&|`<>$) 사용 시 거부. 30초 타임아웃.

    Args:
        command: 실행할 명령 (allowlist 한정)
    """
    return await _tools.execute("bash", {"command": command})


@beta_async_tool
async def recent_research(topic: str) -> str:
    """최신 자료 조사 — Reddit·Hacker News 등에서 최근 한 달 게시물/반응을 수집한다.

    시점에 민감하거나(최신 트렌드·요즘·채택률) 학습 지식으로 답하기 어려운 주제에만 사용.
    출력의 출처 URL 을 근거로 인용할 것.

    Args:
        topic: 조사할 주제
    """
    return await _tools.execute("recent_research", {"topic": topic})


@beta_async_tool
async def vault_search(query: str, limit: int = 10, tags: str = "") -> str:
    """Obsidian vault 의 기존 노트를 query 로 의미 검색 (미가용 시 키워드 폴백).

    매칭 노트의 경로+요약 목록을 반환. 중복 회피용.

    Args:
        query: 검색어
        limit: 최대 결과 수 (기본 10)
        tags: 계층 태그로 검색 범위 한정 (쉼표 구분, 선택). 예: area/devops, tech/qdrant
    """
    return await _tools.execute("vault_search", {"query": query, "limit": limit, "tags": tags})


@beta_async_tool
async def vault_save(
    title: str, content: str, category: str = "", tags: str = "", aliases: str = ""
) -> str:
    """Obsidian vault 에 마크다운 노트(.md)를 저장한다.

    YAML 프론트매터(title/aliases/created/updated/tags/source)를 자동 추가하고 저장 경로를 반환.
    content 본문은 Obsidian 양식(TL;DR 콜아웃·## 구조·위키링크·체크박스·출처)을 따른다.

    Args:
        title: 노트 제목
        content: Obsidian 마크다운 본문
        category: 분류 폴더명 (선택)
        tags: 계층형 중첩 태그를 쉼표로 구분 (선택). 예: type/research, tech/qdrant
        aliases: 동의어·약어를 쉼표로 구분 (선택)
    """
    return await _tools.execute(
        "vault_save",
        {
            "title": title,
            "content": content,
            "category": category,
            "tags": tags,
            "aliases": aliases,
        },
    )


# 라우트별 도구 부분집합 — app.tools.ROUTE_TOOLS(단일 소스) 이름을 데코레이터 객체로 매핑
_SDK_TOOL_BY_NAME = {
    t.name: t for t in (read_file, write_file, bash, recent_research, vault_search, vault_save)
}


def sdk_tools_for(route: str | None) -> list:
    """라우트별 Agent SDK 도구 목록 (tool_runner 의 tools= 인자). 미지정/미지원 라우트는 전체."""
    names = _tools.ROUTE_TOOLS.get(route or "", list(_SDK_TOOL_BY_NAME))
    return [_SDK_TOOL_BY_NAME[n] for n in names if n in _SDK_TOOL_BY_NAME]
