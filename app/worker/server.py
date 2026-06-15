"""작업 실행 워커 HTTP 서버.

봇으로부터 작업 설명을 받아 에이전트에 위임하고,
결과를 봇의 worker-result 엔드포인트로 다시 POST 한다.

POST /run   body: {"task_id": str, "description": str, "save_to_vault": bool}
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
from app.agent.outcome import Outcome
from app.worker import git_ops, metrics, selfcheck, store
from app.worker.agent import _notify, _run_with_tools, plan_and_run, summarize_task

logger = logging.getLogger(__name__)

WORKER_HOST = "0.0.0.0"
WORKER_PORT = int(os.environ.get("WORKER_PORT", "8766"))


@dataclass
class _Job:
    task_id: str
    description: str
    save_to_vault: bool = False


_queue: asyncio.Queue[_Job] = asyncio.Queue(maxsize=0)  # main() 에서 실제 크기로 교체
_semaphore: asyncio.Semaphore = asyncio.Semaphore(1)  # main() 에서 실제 값으로 교체

# 이벤트 루프는 태스크에 약참조만 유지하므로, 참조를 남기지 않으면 실행 중 GC 될 수 있다.
# 강참조를 보관하고 완료 시 자동 제거한다.
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    """백그라운드 태스크를 생성하고 강참조를 보관(완료 시 자동 해제)."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


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
    task_id, description, save_to_vault = job.task_id, job.description, job.save_to_vault
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
                outcome = await plan_and_run(task_id, cleaned)
            except Exception as e:
                logger.exception("플래너 오류 task_id=%s", task_id)
                outcome = Outcome.failure(f"플래너 오류: {type(e).__name__}: {e}")
        else:
            if save_to_vault:
                description = (
                    description
                    + "\n\n[VAULT_SAVE] 작업 완료 후 vault_save 도구로 결과를 Obsidian vault 에 저장하라. "
                    "title은 작업 요약(60자 이내), category·tags를 적절히 지정. "
                    "저장 완료 후 파일 경로를 응답에 포함."
                )
            try:
                outcome = await _run_with_tools(task_id, description)
            except Exception as e:
                logger.exception("작업 처리 중 예외 task_id=%s", task_id)
                outcome = Outcome.failure(f"내부 오류: {type(e).__name__}: {e}")

        failed = not outcome.ok
        await store.set_done(task_id, outcome.text, failed=failed)
        metrics.TASKS_TOTAL.labels(status="failed" if failed else "done").inc()
        await _report_result(task_id, outcome.text)
        logger.info("작업 완료 task_id=%s", task_id)

    # 다음 작업이 참조할 요약본 저장 (계측 구간 밖, 실패해도 무시)
    await _store_summary(task_id, job.description, outcome.text, failed)


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
        _spawn(_run_with_semaphore(job))
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
    save_to_vault = bool(body.get("save_to_vault", False))

    job = _Job(task_id=task_id, description=description, save_to_vault=save_to_vault)
    # DB 행을 먼저 생성한 뒤 큐에 넣는다 — 워커 루프가 set_running(UPDATE) 을
    # create(INSERT) 보다 먼저 실행해 상태/attempts 가 유실되는 경합을 차단.
    await store.create(task_id, description)
    try:
        _queue.put_nowait(job)
    except asyncio.QueueFull:
        return web.Response(status=429, text="큐 가득 참 — 잠시 후 재시도")
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


def _json(payload: dict, status: int = 200) -> web.Response:
    return web.Response(
        status=status,
        content_type="application/json",
        text=json.dumps(payload, ensure_ascii=False),
    )


async def _handle_git_commit(request: web.Request) -> web.Response:
    """로컬 git 커밋. apply=false → 메시지 미리보기, apply=true → 실제 커밋(push 안 함)."""
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="invalid json")

    if bool(body.get("apply", False)):
        message = (body.get("message") or "").strip()
        if not message:
            return web.Response(status=400, text="empty message")
        try:
            head = await git_ops.apply_commit(message)
        except Exception as e:
            logger.exception("git 커밋 실패")
            return _json({"ok": False, "detail": f"{type(e).__name__}: {e}"}, status=500)
        logger.info("git 커밋 완료: %s", head)
        return _json({"ok": True, "detail": head})

    # 미리보기: 변경 수집 + 메시지 생성
    try:
        status, diff = await git_ops.collect_changes()
    except Exception as e:
        logger.exception("git 변경 수집 실패")
        return _json({"detail": f"{type(e).__name__}: {e}"}, status=500)
    if not status:
        return _json({"has_changes": False})
    try:
        message = await git_ops.generate_message(status, diff)
    except Exception as e:
        logger.exception("커밋 메시지 생성 실패")
        return _json({"detail": f"{type(e).__name__}: {e}"}, status=500)
    return _json({"has_changes": True, "message": message, "summary": status})


async def _handle_git_push(request: web.Request) -> web.Response:
    """원격 push. apply=false → 대기 커밋 미리보기, apply=true → 실제 push."""
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="invalid json")

    try:
        branch = await git_ops.current_branch()
    except Exception as e:
        logger.exception("브랜치 조회 실패")
        return _json({"detail": f"{type(e).__name__}: {e}"}, status=500)

    if bool(body.get("apply", False)):
        try:
            detail = await git_ops.push(branch)
        except Exception as e:
            logger.warning("git push 실패: %s", e)  # 메시지는 git_ops 에서 토큰 redact 됨
            return _json({"ok": False, "detail": f"{type(e).__name__}: {e}"}, status=500)
        logger.info("git push 완료: %s", branch)
        return _json({"ok": True, "detail": detail})

    # 미리보기
    if not config.GITHUB_TOKEN:
        return _json(
            {
                "ready": False,
                "branch": branch,
                "detail": "GITHUB_TOKEN 미설정 — .env 에 PAT 추가 필요",
            }
        )
    pending = await git_ops.pending_commits(branch)
    if pending == "":
        return _json({"ready": False, "branch": branch, "detail": "이미 최신 — push 할 커밋 없음"})
    preview = "origin 에 신규 브랜치로 push 됩니다" if pending is None else pending
    return _json({"ready": True, "branch": branch, "pending": preview})


async def _handle_vault_reindex(_request: web.Request) -> web.Response:
    """vault 의 모든 .md 노트를 벡터 인덱스에 재인덱싱하고 MOC/Dashboard 를 갱신."""
    from app.rag import moc, vault_index
    from app.tools import filesystem

    vault_dir = filesystem.WORKSPACE / config.VAULT_SUBDIR
    if not vault_dir.is_dir():
        return _json({"ok": False, "detail": "vault 폴더 없음"}, status=404)
    # 임베딩+네트워크는 동기·블로킹 → 이벤트 루프 밖 스레드에서 실행
    count = await asyncio.to_thread(vault_index.index_all, vault_dir)
    if count is None:
        cause = vault_index.last_error() or "원인 미상 (워커 로그 확인)"
        return _json({"ok": False, "detail": f"벡터 인덱스 미가용 — {cause}"}, status=503)
    # MOC/Dashboard 재생성 (인덱스와 무관하게 동작 — 실패해도 인덱싱 결과는 유효)
    moc_count = await asyncio.to_thread(moc.build_moc, vault_dir)
    return _json({"ok": True, "indexed": count, "moc": moc_count})


async def _handle_health(_request: web.Request) -> web.Response:
    return web.Response(status=200, text="ok")


async def _handle_selfcheck(_request: web.Request) -> web.Response:
    """런타임 의존성 자가점검 결과(JSON). 실패 항목이 있으면 503."""
    checks = await selfcheck.run_checks()
    all_ok = all(c["ok"] for c in checks)
    return _json({"ok": all_ok, "checks": checks}, status=200 if all_ok else 503)


async def _handle_digest(_request: web.Request) -> web.Response:
    """최근 vault 노트를 요약한 주간 브리핑 노트를 즉시 생성 (봇 /digest)."""
    from app.worker import digest

    result = await digest.generate_digest()
    ok = result.startswith("저장 완료")
    return _json({"ok": ok, "detail": result}, status=200 if ok else 500)


async def _digest_loop() -> None:
    """DIGEST_ENABLED 시 주기적으로 다이제스트를 생성하고 봇에 알림 (어떤 실패에도 루프 지속)."""
    from app.agent import runtime
    from app.worker import digest

    interval = max(1, config.DIGEST_INTERVAL_DAYS) * 86400
    while True:
        await asyncio.sleep(interval)
        try:
            result = await digest.generate_digest()
            await runtime._notify(f"🗞️ 주간 브리핑 생성: {result}")
        except Exception as e:  # noqa: BLE001 — 스케줄 루프는 중단되면 안 됨
            logger.warning("다이제스트 생성 실패: %s", e)


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
    app.router.add_post("/git/commit", _handle_git_commit)
    app.router.add_post("/git/push", _handle_git_push)
    app.router.add_post("/vault/reindex", _handle_vault_reindex)
    app.router.add_post("/digest", _handle_digest)
    app.router.add_get("/tasks", _handle_tasks)
    app.router.add_get("/health", _handle_health)
    app.router.add_get("/selfcheck", _handle_selfcheck)
    app.router.add_get("/metrics", metrics.handle_metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WORKER_HOST, WORKER_PORT)
    await site.start()

    _spawn(_worker_loop())
    if config.DIGEST_ENABLED:
        _spawn(_digest_loop())
        logger.info("정기 다이제스트 활성: %d일 주기", config.DIGEST_INTERVAL_DAYS)

    logger.info("워커 시작: http://%s:%d", WORKER_HOST, WORKER_PORT)
    logger.info(
        "설정: model=%s max_iter=%d timeout=%.0fs concurrent=%d queue=%d",
        config.WORKER_MODEL,
        config.WORKER_MAX_ITERATIONS,
        config.WORKER_TIMEOUT_S,
        config.WORKER_MAX_CONCURRENT,
        config.WORKER_QUEUE_SIZE,
    )

    # 기동 자가점검 — 런타임 의존성 상태를 로그로 (비차단). 상세는 GET /selfcheck.
    for c in await selfcheck.run_checks():
        icon = "🟢" if c["ok"] else "🔴"
        log = logger.info if c["ok"] else logger.warning
        log("자가점검 %s %s: %s", icon, c["name"], c["detail"])

    stop = asyncio.Event()
    try:
        await stop.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
