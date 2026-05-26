"""작업 실행 워커 HTTP 서버.

봇으로부터 작업 설명을 받아 에이전트에 위임하고,
결과를 봇의 worker-result 엔드포인트로 다시 POST 한다.

POST /run  body: {"task_id": str, "description": str}
  → 202 accepted  (백그라운드 처리)
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

import aiohttp
from aiohttp import web

from app import config
from app.worker.agent import _notify, _run_with_tools

logger = logging.getLogger(__name__)

WORKER_HOST = "0.0.0.0"
WORKER_PORT = int(os.environ.get("WORKER_PORT", "8766"))


async def _report_result(task_id: str, result: str) -> None:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                config.WORKER_BOT_RESULT_URL,
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


async def _process_task(task_id: str, description: str, upload_to_notion: bool = False) -> None:
    logger.info("작업 시작 task_id=%s desc=%r", task_id, description[:80])
    short_desc = description[:200] + ("…" if len(description) > 200 else "")
    await _notify(f"⚙️ *작업 처리 시작* (id=`{task_id}`)\n{short_desc}")

    if upload_to_notion and config.NOTION_TOKEN and config.NOTION_PARENT_PAGE_ID:
        description = (
            description
            + "\n\n[NOTION_SAVE] 작업 완료 후 notion_create_page 도구로 결과를 저장하라. "
            "title은 작업 요약(60자 이내), icon='📋'. 저장 완료 후 페이지 URL을 응답에 포함."
        )

    try:
        result = await _run_with_tools(task_id, description)
    except Exception as e:
        logger.exception("작업 처리 중 예외 task_id=%s", task_id)
        result = f"(내부 오류: {type(e).__name__}: {e})"

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
    upload_to_notion = bool(body.get("upload_to_notion", False))

    asyncio.create_task(_process_task(task_id, description, upload_to_notion))
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
        config.WORKER_MODEL,
        config.WORKER_MAX_ITERATIONS,
        config.WORKER_TIMEOUT_S,
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
