"""시나리오 러너 — production 코드를 monkeypatch 로 감싸 게이트웨이를 1회 실행.

patch 대상(전부 런타임 한정, app/ 소스 불변):
  config.CLAUDE_API_KEY      run_task 의 백엔드 가드 통과용 더미
  runtime.select_backend     'claude' 고정(비교 가능성)
  runtime._claude_client     ReplayClient(cassette)
  runtime.execute            ToolRecorder(부작용 차단 + 호출 기록)
  runtime._notify/graph._notify  no-op
  graph._retrieve/_recent_memory_block  '' (RAG·DB 차단)
  graph._route               원본 호출 + 선택된 route 캡처
"""

from __future__ import annotations

import contextlib
from unittest.mock import patch

from app import config
from app.agent import graph, runtime
from evals.llm_io import ReplayClient
from evals.stubs import ToolRecorder, empty_str, noop_notify
from evals.trace import AgentTrace


def _const_claude():
    async def _select(*_args, **_kwargs) -> str:
        return "claude"

    return _select


async def run_scenario(scenario: dict, mode: str = "replay") -> AgentTrace:
    """시나리오(JSON dict)를 1회 실행하고 AgentTrace 를 반환.

    mode='replay' : LLM=cassette(무과금·결정론). mode='live' : 실 Claude 호출(과금).
    두 모드 모두 도구는 스텁(canned)으로 부작용을 차단한다.
    """
    trace = AgentTrace()
    recorder = ToolRecorder(scenario.get("tool_outputs", {}))

    real_route = graph._route

    async def route_capture(task_id: str, description: str):
        result = await real_route(task_id, description)
        trace.route = result[0]
        return result

    with contextlib.ExitStack() as es:
        e = es.enter_context
        e(patch.object(runtime, "execute", recorder.execute))
        e(patch.object(runtime, "_notify", noop_notify))
        e(patch.object(graph, "_notify", noop_notify))
        e(patch.object(graph, "_retrieve", empty_str))
        e(patch.object(graph, "_recent_memory_block", empty_str))
        e(patch.object(graph, "_route", route_capture))

        if mode == "replay":
            client = ReplayClient(scenario.get("llm", []))
            e(patch.object(config, "CLAUDE_API_KEY", "eval-dummy-key"))
            e(patch.object(runtime, "select_backend", _const_claude()))
            e(patch.object(runtime, "_claude_client", lambda: client))

        outcome = await graph.run_task("eval", scenario["input"])

    trace.tool_calls = recorder.calls
    trace.output = outcome.text
    trace.ok = outcome.ok
    return trace
