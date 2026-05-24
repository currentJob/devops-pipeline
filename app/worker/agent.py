"""Claude tool-use 루프 에이전트.

작업 설명을 받아 Claude 와 tool-use 루프를 돌며 처리.
도구 실행은 app.tools 를 통해 위임.
"""

from __future__ import annotations

import logging
import os
import time

import aiohttp
import anthropic

from app import config, tools

logger = logging.getLogger(__name__)

BOT_NOTIFY_URL = os.environ.get("BOT_NOTIFY_URL", "http://bot:8765/notify")
MODEL = os.environ.get("WORKER_MODEL", "claude-haiku-4-5-20251001")
MAX_TOKENS = int(os.environ.get("WORKER_MAX_TOKENS", "8192"))
MAX_ITERATIONS = int(os.environ.get("WORKER_MAX_ITERATIONS", "10"))
TIMEOUT_S = float(os.environ.get("WORKER_TIMEOUT_S", "120"))

SYSTEM_PROMPT = """당신은 DevOps/IaC 자동화 어시스턴트입니다.

사용 가능한 도구:
- read_file(path): 프로젝트 파일 읽기 (전체 워크스페이스 읽기 가능)
- write_file(path, content): prompts/output/ 하위에만 쓰기 가능
- bash(command): 허용된 명령만 (ls, cat, git status/diff/log, uv run pytest/ruff/pip-audit, docker compose ps/logs)
- notion_search(query, limit): Notion 워크스페이스 페이지 검색
- notion_create_page(title, content, icon): NOTION_PARENT_PAGE_ID 하위에 새 페이지 생성

원칙:
1. 추측 금지 — 도구로 사실 확인 후 응답.
2. 코드 변경이 필요하면 prompts/output/ 에 권고 문서를 작성하고, 사용자가 수동 적용하도록 안내.
3. 간결하게 — 핵심만 보고, 불필요한 메타 설명 생략.

특수 task prefix:
- "[STACK_TASK]" 로 시작하는 description 은 IT 트렌드 페이지 생성 워크플로.
  반드시 task 본문의 절차를 그대로 따르고, 마지막에는 생성된 Notion 페이지 URL 만 응답.
"""


async def _notify(text: str) -> None:
    """봇 /notify 로 중간 이벤트 알림 전송 (실패해도 작업 계속)."""
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                BOT_NOTIFY_URL,
                json={"text": text},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp,
        ):
            if resp.status != 200:
                logger.warning("중간 알림 비-200: %s", resp.status)
    except aiohttp.ClientError as e:
        logger.warning("중간 알림 실패: %s", e)


def _format_tool_call(name: str, args: dict) -> str:
    if name == "bash":
        return f"`{args.get('command', '')}`"
    if name in ("read_file", "write_file"):
        return f"`{args.get('path', '')}`"
    if name == "notion_search":
        return f"query: `{args.get('query', '')}`"
    if name == "notion_create_page":
        return f"title: `{args.get('title', '')}`"
    return str(args)[:120]


def _extract_text(content_blocks) -> str:
    parts = []
    for block in content_blocks:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


async def _run_with_tools(task_id: str, prompt: str) -> str:
    if not config.CLAUDE_API_KEY:
        return "(Claude API 키 미설정 — .env 의 CLAUDE_API_KEY 추가 필요)"

    client = anthropic.AsyncAnthropic(api_key=config.CLAUDE_API_KEY)
    messages: list[dict] = [{"role": "user", "content": prompt}]
    start = time.monotonic()

    for iteration in range(MAX_ITERATIONS):
        elapsed = time.monotonic() - start
        if elapsed > TIMEOUT_S:
            return f"(타임아웃: {elapsed:.1f}s > {TIMEOUT_S}s)"

        try:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=tools.TOOLS_SCHEMA,
                messages=messages,
            )
        except anthropic.APIError as e:
            logger.warning("Claude API 오류 iteration=%d: %s", iteration, e)
            return f"(Claude API 오류: {e})"

        if response.stop_reason == "end_turn":
            return _extract_text(response.content) or "(빈 응답)"

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("도구 호출 iter=%d name=%s", iteration, block.name)
                    detail = _format_tool_call(block.name, block.input)
                    await _notify(
                        f"🔧 *{block.name}* (id=`{task_id}`, step {iteration + 1})\n{detail}"
                    )
                    result = await tools.execute(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
            continue

        return f"(예상하지 못한 stop_reason: {response.stop_reason})"

    return f"(최대 반복 횟수 {MAX_ITERATIONS}회 초과)"
