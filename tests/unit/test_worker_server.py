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
