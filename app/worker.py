"""작업 실행 워커.

봇으로부터 작업 설명을 받아 Claude tool use 루프로 처리하고,
결과를 봇의 worker-result 엔드포인트로 다시 POST 한다.

도구: read_file, write_file (prompts/output/ 한정), bash (화이트리스트)
한도: 최대 10회 도구 호출 + 120초 시간

POST /run  body: {"task_id": str, "description": str}
  → 202 accepted  (백그라운드 처리)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid

import aiohttp
import anthropic
from aiohttp import web

from app import config, tools

logger = logging.getLogger(__name__)

WORKER_HOST = "0.0.0.0"
WORKER_PORT = int(os.environ.get("WORKER_PORT", "8766"))
BOT_RESULT_URL = os.environ.get("BOT_RESULT_URL", "http://bot:8765/worker-result")
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


# ── tool use 루프 ────────────────────────────────────────────────────────────


async def _run_with_tools(prompt: str) -> str:
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


def _extract_text(content_blocks) -> str:
    parts = []
    for block in content_blocks:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


# ── 봇 결과 보고 ─────────────────────────────────────────────────────────────


async def _report_result(task_id: str, result: str) -> None:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                BOT_RESULT_URL,
                json={"task_id": task_id, "result": result},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        "결과 전송 비-200 task_id=%s status=%s body=%s",
                        task_id,
                        resp.status,
                        body,
                    )
        except aiohttp.ClientError as e:
            logger.error("결과 전송 실패 task_id=%s: %s", task_id, e)


# ── 작업 처리 ────────────────────────────────────────────────────────────────


async def _process_task(task_id: str, description: str) -> None:
    logger.info("작업 시작 task_id=%s desc=%r", task_id, description[:80])
    result = await _run_with_tools(description)
    await _report_result(task_id, result)
    logger.info("작업 완료 task_id=%s", task_id)


async def _handle_run(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="invalid json")

    task_id = body.get("task_id") or str(uuid.uuid4())[:8]
    description = (body.get("description") or "").strip()
    if not description:
        return web.Response(status=400, text="empty description")

    asyncio.create_task(_process_task(task_id, description))
    logger.info("작업 큐 등록 task_id=%s", task_id)
    return web.Response(status=202, text=task_id)


async def _handle_health(_request: web.Request) -> web.Response:
    return web.Response(status=200, text="ok")


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = web.Application()
    app.router.add_post("/run", _handle_run)
    app.router.add_get("/health", _handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WORKER_HOST, WORKER_PORT)
    await site.start()
    logger.info("워커 시작: http://%s:%d", WORKER_HOST, WORKER_PORT)
    logger.info(
        "tool use 설정: model=%s max_iter=%d timeout=%.0fs",
        MODEL,
        MAX_ITERATIONS,
        TIMEOUT_S,
    )

    stop = asyncio.Event()
    try:
        await stop.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
