"""LLM 런타임(runtime.run_agent / chat) 단위 테스트 — 모킹, 네트워크 없음.

run_agent 의 Claude 경로는 Anthropic Agent SDK 의 tool_runner 를 사용하므로,
client.beta.messages.tool_runner 가 돌려주는 비동기 이터러블 runner 를 모사한다.
"""

from __future__ import annotations

import pytest

from app import config
from app.agent import runtime


class _Block:
    def __init__(self, type, text=None, name=None, input=None, id=None):
        self.type = type
        self.text = text
        self.name = name
        self.input = input
        self.id = id


class _Msg:
    def __init__(self, content):
        self.content = content


class _FakeRunner:
    """tool_runner 모사 — 각 모델 턴을 yield 하고 tool_use 를 executor 로 실행."""

    def __init__(self, messages, executor):
        self._messages = messages
        self._executor = executor

    async def __aiter__(self):
        for m in self._messages:
            yield m
            for b in m.content:
                if b.type == "tool_use":
                    await self._executor(b.name, b.input)


class _FakeBetaMessages:
    def __init__(self, runner):
        self._runner = runner

    def tool_runner(self, **_kw):
        return self._runner


class _FakeMessages:
    """chat() 용 단일 완성 모사."""

    def __init__(self, responses):
        self._responses = list(responses)

    async def create(self, **_kw):
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


class _FakeClient:
    def __init__(self, runner=None, create_responses=None):
        self.beta = type("_B", (), {"messages": _FakeBetaMessages(runner)})()
        self.messages = _FakeMessages(create_responses or [])


@pytest.fixture(autouse=True)
def _claude_backend(monkeypatch):
    # VLLM 미설정 + Claude 키 → select_backend 가 'claude' (네트워크 없이)
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "")
    monkeypatch.setattr(config, "CLAUDE_API_KEY", "sk-test")
    monkeypatch.setattr(config, "WORKER_MAX_ITERATIONS", 3)

    async def _noop(_text):
        return None

    monkeypatch.setattr(runtime, "_notify", _noop)


def _patch_runner(monkeypatch, messages, executor):
    client = _FakeClient(runner=_FakeRunner(messages, executor))
    monkeypatch.setattr(runtime, "_claude_client", lambda: client)
    return client


@pytest.mark.asyncio
async def test_run_agent_tool_then_finish(monkeypatch):
    calls = []

    async def executor(name, args):
        calls.append((name, args))
        return "FILE CONTENTS"

    _patch_runner(
        monkeypatch,
        [
            _Msg([_Block("tool_use", name="read_file", input={"path": "x"}, id="t1")]),
            _Msg([_Block("text", text="분석 완료")]),
        ],
        executor,
    )
    result = await runtime.run_agent("code", "sys", "user", "tid")
    assert result == "분석 완료"
    assert calls == [("read_file", {"path": "x"})]


@pytest.mark.asyncio
async def test_run_agent_no_tools(monkeypatch):
    async def executor(_name, _args):
        raise AssertionError("도구가 호출되면 안 됨")

    _patch_runner(monkeypatch, [_Msg([_Block("text", text="바로 답")])], executor)
    assert await runtime.run_agent("general", "sys", "user", "tid") == "바로 답"


@pytest.mark.asyncio
async def test_run_agent_max_iter_returns_fallback(monkeypatch):
    # runner 가 최종 텍스트 없이 종료(최대 반복 도달 모사) → 폴백 문구 반환
    async def executor(_name, _args):
        return "loop"

    _patch_runner(
        monkeypatch,
        [_Msg([_Block("tool_use", name="bash", input={"command": "ls"}, id="t")])],
        executor,
    )
    result = await runtime.run_agent("code", "sys", "user", "tid")
    assert "최대 반복" in result


@pytest.mark.asyncio
async def test_run_agent_returns_partial_text(monkeypatch):
    # 최종 end_turn 없이 종료해도, 도구 호출과 함께 나온 직전 텍스트를 폐기하지 않고 반환
    async def executor(_name, _args):
        return "loop"

    _patch_runner(
        monkeypatch,
        [
            _Msg(
                [
                    _Block("text", text="중간 분석 결과"),
                    _Block("tool_use", name="bash", input={"command": "ls"}, id="t"),
                ]
            )
        ],
        executor,
    )
    result = await runtime.run_agent("code", "sys", "user", "tid")
    assert result == "중간 분석 결과"


@pytest.mark.asyncio
async def test_chat_returns_text(monkeypatch):
    client = _FakeClient(create_responses=[_Msg([_Block("text", text="요약문")])])
    monkeypatch.setattr(runtime, "_claude_client", lambda: client)
    assert await runtime.chat("system", "user") == "요약문"
