"""worker.server HTTP 핸들러·백그라운드 태스크 단위 테스트."""

from __future__ import annotations

import asyncio

from app.worker import server


class _FakeRequest:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self) -> dict:
        return self._payload


async def test_handle_run_creates_before_enqueue(monkeypatch):
    """store.create 가 큐 등록보다 먼저 실행되어야 한다 (상태 경합 방지)."""
    order: list[tuple[str, int]] = []

    async def fake_create(task_id: str, description: str) -> None:
        # create 시점의 큐 크기를 기록 — 0 이어야 create 가 enqueue 보다 앞섬
        order.append(("create", server._queue.qsize()))

    monkeypatch.setattr(server.store, "create", fake_create)
    monkeypatch.setattr(server.metrics.QUEUE_SIZE, "set", lambda _v: None)
    server._queue = asyncio.Queue(maxsize=10)

    resp = await server._handle_run(_FakeRequest({"task_id": "t1", "description": "hi"}))

    assert resp.status == 202
    assert order == [("create", 0)]
    assert server._queue.qsize() == 1


async def test_handle_run_queue_full_returns_429(monkeypatch):
    async def fake_create(task_id: str, description: str) -> None:
        pass

    monkeypatch.setattr(server.store, "create", fake_create)
    monkeypatch.setattr(server.metrics.QUEUE_SIZE, "set", lambda _v: None)
    server._queue = asyncio.Queue(maxsize=1)
    server._queue.put_nowait(server._Job("x", "busy"))

    resp = await server._handle_run(_FakeRequest({"description": "hi"}))
    assert resp.status == 429


async def test_handle_run_rejects_empty_description(monkeypatch):
    resp = await server._handle_run(_FakeRequest({"description": "   "}))
    assert resp.status == 400


async def test_worker_loop_limits_concurrency_and_queues_excess(monkeypatch):
    """슬롯 선확보로 동시 실행은 max_concurrent 로 제한되고 초과분은 큐에 남는다."""
    server._semaphore = asyncio.Semaphore(1)
    server._queue = asyncio.Queue(maxsize=5)
    monkeypatch.setattr(server.metrics.QUEUE_SIZE, "set", lambda _v: None)

    running = 0
    max_running = 0
    started = asyncio.Semaphore(0)  # 작업 시작 시그널
    release = asyncio.Event()

    async def fake_process(_job):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        started.release()
        await release.wait()
        running -= 1

    monkeypatch.setattr(server, "_process_task", fake_process)

    loop_task = asyncio.create_task(server._worker_loop())
    try:
        for i in range(3):
            server._queue.put_nowait(server._Job(f"t{i}", "d"))
        await asyncio.wait_for(started.acquire(), timeout=1)  # 첫 작업 시작 대기
        await asyncio.sleep(0.05)  # 두 번째가 (잘못) 시작될 여유를 주고 확인

        assert max_running == 1  # 동시 실행 1개로 제한
        assert server._queue.qsize() == 2  # 나머지는 큐에 — 백프레셔 유효
    finally:
        release.set()
        loop_task.cancel()


async def test_spawn_keeps_strong_reference_until_done():
    done = asyncio.Event()

    async def work() -> None:
        done.set()

    task = server._spawn(work())
    assert task in server._background_tasks  # 실행 중에는 강참조 보관

    await done.wait()
    await task
    await asyncio.sleep(0)  # done_callback(call_soon) 실행 기회
    assert task not in server._background_tasks  # 완료 시 자동 제거
