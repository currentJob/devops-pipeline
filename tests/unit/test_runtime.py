"""네이티브 LLM 런타임(runtime.run_agent / chat) 단위 테스트 — 모킹, 네트워크 없음."""

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

    def model_dump(self):
        d = {"type": self.type}
        if self.type == "text":
            d["text"] = self.text
        else:
            d.update({"id": self.id, "name": self.name, "input": self.input})
        return d


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def create(self, **_kw):
        self.calls += 1
        # 마지막 1개는 소진하지 않고 계속 반환 (max-iter 테스트용)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


class _FakeClient:
    def __init__(self, responses):
        self.messages = _FakeMessages(responses)


@pytest.fixture(autouse=True)
def _claude_backend(monkeypatch):
    # VLLM 미설정 + Claude 키 → select_backend 가 'claude' (네트워크 없이)
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "")
    monkeypatch.setattr(config, "CLAUDE_API_KEY", "sk-test")
    monkeypatch.setattr(config, "WORKER_MAX_ITERATIONS", 3)

    async def _noop(_text):
        return None

    monkeypatch.setattr(runtime, "_notify", _noop)


def _patch_client(monkeypatch, responses):
    client = _FakeClient(responses)
    monkeypatch.setattr(runtime, "_claude_client", lambda: client)
    return client


@pytest.mark.asyncio
async def test_run_agent_tool_then_finish(monkeypatch):
    calls = []

    async def fake_execute(name, args):
        calls.append((name, args))
        return "FILE CONTENTS"

    monkeypatch.setattr(runtime, "execute", fake_execute)
    _patch_client(
        monkeypatch,
        [
            _Resp("tool_use", [_Block("tool_use", name="read_file", input={"path": "x"}, id="t1")]),
            _Resp("end_turn", [_Block("text", text="분석 완료")]),
        ],
    )
    result = await runtime.run_agent("code", "sys", "user", "tid")
    assert result == "분석 완료"
    assert calls == [("read_file", {"path": "x"})]


@pytest.mark.asyncio
async def test_run_agent_no_tools(monkeypatch):
    monkeypatch.setattr(runtime, "execute", None)  # 호출되면 안 됨
    _patch_client(monkeypatch, [_Resp("end_turn", [_Block("text", text="바로 답")])])
    assert await runtime.run_agent("general", "sys", "user", "tid") == "바로 답"


@pytest.mark.asyncio
async def test_run_agent_max_iter_guard(monkeypatch):
    async def fake_execute(_name, _args):
        return "loop"

    monkeypatch.setattr(runtime, "execute", fake_execute)
    client = _patch_client(
        monkeypatch,
        [_Resp("tool_use", [_Block("tool_use", name="bash", input={"command": "ls"}, id="t")])],
    )
    result = await runtime.run_agent("code", "sys", "user", "tid")
    assert "최대 반복" in result
    assert client.messages.calls == config.WORKER_MAX_ITERATIONS


@pytest.mark.asyncio
async def test_chat_returns_text(monkeypatch):
    _patch_client(monkeypatch, [_Resp("end_turn", [_Block("text", text="요약문")])])
    assert await runtime.chat("system", "user") == "요약문"
