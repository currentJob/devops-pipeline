"""Outcome 값 객체 + run_task/run_plan_task 의 명시적 성공/실패 반환 테스트.

괄호 문자열 휴리스틱을 대체한 Outcome 타입이 올바르게 전파되는지 검증.
"""

from __future__ import annotations

from app import config
from app.agent import graph
from app.agent.outcome import Outcome
from app.worker.store import TaskStatus


def test_outcome_factories():
    assert Outcome.success("ok") == Outcome(True, "ok")
    assert Outcome.failure("no") == Outcome(False, "no")


def test_task_status_values():
    assert TaskStatus.PENDING.value == "pending"
    assert [s.value for s in TaskStatus] == ["pending", "running", "done", "failed"]


async def test_run_task_no_backend_returns_failure(monkeypatch):
    monkeypatch.setattr(config, "CLAUDE_API_KEY", "")
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "")
    out = await graph.run_task("t1", "작업")
    assert isinstance(out, Outcome)
    assert out.ok is False
    assert "백엔드" in out.text


async def test_run_plan_task_ok_when_all_subtasks_succeed(monkeypatch):
    monkeypatch.setattr(config, "CLAUDE_API_KEY", "key")

    async def _fake_plan(task_id, desc):
        return ["a", "b"]

    async def _fake_run_task(task_id, sub):
        return Outcome.success(f"done {sub}")

    async def _noop_notify(text):
        pass

    monkeypatch.setattr(graph, "_plan", _fake_plan)
    monkeypatch.setattr(graph, "run_task", _fake_run_task)
    monkeypatch.setattr(graph, "_notify", _noop_notify)

    out = await graph.run_plan_task("t1", "복합")
    assert out.ok is True
    assert "done a" in out.text and "done b" in out.text


async def test_run_plan_task_failed_if_any_subtask_fails(monkeypatch):
    monkeypatch.setattr(config, "CLAUDE_API_KEY", "key")

    async def _fake_plan(task_id, desc):
        return ["a", "b"]

    seen = {"n": 0}

    async def _fake_run_task(task_id, sub):
        seen["n"] += 1
        return Outcome.success("ok") if seen["n"] == 1 else Outcome.failure("boom")

    async def _noop_notify(text):
        pass

    monkeypatch.setattr(graph, "_plan", _fake_plan)
    monkeypatch.setattr(graph, "run_task", _fake_run_task)
    monkeypatch.setattr(graph, "_notify", _noop_notify)

    out = await graph.run_plan_task("t1", "복합")
    assert out.ok is False  # 하위 작업 하나라도 실패 → 플랜 실패
