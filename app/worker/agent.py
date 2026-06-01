"""Worker agent — app.agent.graph 의 얇은 래퍼.

server.py 가 기대하는 _notify / _run_with_tools / plan_and_run 인터페이스를 유지.
실제 AI 로직은 app/agent/graph.py (LangGraph) 에서 처리.
"""
from __future__ import annotations

from app.agent.graph import _notify, run_plan_task, run_task


async def _run_with_tools(task_id: str, prompt: str) -> str:
    return await run_task(task_id, prompt)


async def plan_and_run(task_id: str, description: str) -> str:
    return await run_plan_task(task_id, description)


__all__ = ["_notify", "_run_with_tools", "plan_and_run"]
