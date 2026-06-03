"""작업 실행 워커 HTTP 서버.

봇으로부터 작업 설명을 받아 에이전트에 위임하고,
결과를 봇의 worker-result 엔드포인트로 다시 POST 한다.

POST /run   body: {"task_id": str, "description": str, "upload_to_notion": bool}
  → 202 accepted  (백그라운드 처리)
  → 429 큐 가득 참

GET  /tasks?limit=N
  → 200 JSON 작업 이력

GET  /health
  → 200 ok
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass

import aiohttp
from aiohttp import web

from app import config
from app.worker import metrics, store
from app.worker.agent import _notify, _run_with_tools, plan_and_run, summarize_task

logger = logging.getLogger(__name__)

WORKER_HOST = "0.0.0.0"
WORKER_PORT = int(os.environ.get("WORKER_PORT", "8766"))


@dataclass
class _Job:
    task_id: str
    description: str
    upload_to_notion: bool = False


_queue: asyncio.Queue[_Job] = asyncio.Queue(maxsize=0)  # main() 에서 실제 크기로 교체
_semaphore: asyncio.Semaphore = asyncio.Semaphore(1)  # main() 에서 실제 값으로 교체


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


async def _process_task(job: _Job) -> None:
    task_id, description, upload_to_notion = job.task_id, job.description, job.upload_to_notion
    logger.info("작업 시작 task_id=%s desc=%r", task_id, description[:80])

    # 처리 시간 + 동시 처리 수 계측 (예외/조기반환에도 게이지 복구)
    with metrics.INFLIGHT.track_inprogress(), metrics.TASK_DURATION.time():
        await store.set_running(task_id)
        short_desc = description[:200] + ("…" if len(description) > 200 else "")
        await _notify(f"⚙️ *작업 처리 시작* (id=`{task_id}`)\n{short_desc}")

        # [PLAN_TASK]: 분해 후 순차 실행
        if description.startswith("[PLAN_TASK]"):
            cleaned = description[len("[PLAN_TASK]") :].strip()
            try:
                result = await plan_and_run(task_id, cleaned)
            except Exception as e:
                logger.exception("플래너 오류 task_id=%s", task_id)
                result = f"(플래너 오류: {type(e).__name__}: {e})"
        else:
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

        failed = result.startswith("(") and result.endswith(")")
        await store.set_done(task_id, result, failed=failed)
        metrics.TASKS_TOTAL.labels(status="failed" if failed else "done").inc()
        await _report_result(task_id, result)
        logger.info("작업 완료 task_id=%s", task_id)

    # 다음 작업이 참조할 요약본 저장 (계측 구간 밖, 실패해도 무시)
    await _store_summary(task_id, job.description, result, failed)


async def _store_summary(task_id: str, description: str, result: str, failed: bool) -> None:
    """완료 작업의 요약을 저장. 실패 작업은 LLM 호출 없이 결과 앞부분만."""
    try:
        summary = result[:200] if failed else await summarize_task(description, result)
        await store.set_summary(task_id, summary)
    except Exception as e:
        logger.warning("작업 요약 저장 실패 task_id=%s: %s", task_id, e)


async def _worker_loop() -> None:
    """큐에서 작업을 꺼내 세마포어로 동시성을 제어하며 실행."""
    while True:
        job = await _queue.get()
        metrics.QUEUE_SIZE.set(_queue.qsize())
        asyncio.create_task(_run_with_semaphore(job))
        _queue.task_done()


async def _run_with_semaphore(job: _Job) -> None:
    async with _semaphore:
        await _process_task(job)


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

    job = _Job(task_id=task_id, description=description, upload_to_notion=upload_to_notion)
    try:
        _queue.put_nowait(job)
    except asyncio.QueueFull:
        return web.Response(status=429, text="큐 가득 참 — 잠시 후 재시도")

    await store.create(task_id, description)
    metrics.QUEUE_SIZE.set(_queue.qsize())
    logger.info("작업 큐 등록 task_id=%s", task_id)
    return web.Response(status=202, text=task_id)


async def _handle_tasks(request: web.Request) -> web.Response:
    try:
        limit = int(request.rel_url.query.get("limit", "10"))
    except ValueError:
        limit = 10
    tasks = await store.get_recent(min(limit, 50))
    return web.Response(
        status=200,
        content_type="application/json",
        text=json.dumps(tasks, ensure_ascii=False),
    )


async def _handle_health(_request: web.Request) -> web.Response:
    return web.Response(status=200, text="ok")


async def main() -> None:
    global _queue, _semaphore

    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    await store.init()
    _queue = asyncio.Queue(maxsize=config.WORKER_QUEUE_SIZE)
    _semaphore = asyncio.Semaphore(config.WORKER_MAX_CONCURRENT)

    app = web.Application()
    app.router.add_post("/run", _handle_run)
    app.router.add_get("/tasks", _handle_tasks)
    app.router.add_get("/health", _handle_health)
    app.router.add_get("/metrics", metrics.handle_metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WORKER_HOST, WORKER_PORT)
    await site.start()

    asyncio.create_task(_worker_loop())

    logger.info("워커 시작: http://%s:%d", WORKER_HOST, WORKER_PORT)
    logger.info(
        "설정: model=%s max_iter=%d timeout=%.0fs concurrent=%d queue=%d",
        config.WORKER_MODEL,
        config.WORKER_MAX_ITERATIONS,
        config.WORKER_TIMEOUT_S,
        config.WORKER_MAX_CONCURRENT,
        config.WORKER_QUEUE_SIZE,
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
