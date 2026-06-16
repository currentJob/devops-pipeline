"""녹화/재생 LLM — Claude(AsyncAnthropic) 클라이언트의 가짜 구현.

runtime._claude_client() 를 이 ReplayClient 로 패치하면, runtime.chat / _run_claude 가
실제 API 대신 cassette(녹화된 응답 리스트)를 호출 순서대로 돌려받는다.
응답 객체는 anthropic Messages API 의 shape(.content[*].type/.text/.name/.input/.id,
.model_dump(), .stop_reason)를 모사한다. vLLM 경로는 select_backend='claude' 고정으로 미사용.
"""

from __future__ import annotations


class _Block:
    """anthropic content block 모사 (text | tool_use)."""

    def __init__(self, data: dict):
        self._data = data
        self.type = data["type"]
        self.text = data.get("text", "")
        self.name = data.get("name", "")
        self.input = data.get("input", {})
        self.id = data.get("id", "")

    def model_dump(self) -> dict:
        return dict(self._data)


class _Response:
    def __init__(self, data: dict):
        self.content = [_Block(b) for b in data.get("content", [])]
        self.stop_reason = data.get("stop_reason", "end_turn")


class _Messages:
    def __init__(self, responses: list[dict]):
        self._responses = responses
        self._i = 0

    async def create(self, **_kwargs) -> _Response:
        if self._i >= len(self._responses):
            raise AssertionError(
                f"cassette 소진 — 녹화 응답 {len(self._responses)}개보다 LLM 호출이 많음. "
                "cassette('llm')를 보강하거나 record 로 재녹화하세요."
            )
        resp = self._responses[self._i]
        self._i += 1
        return _Response(resp)


class ReplayClient:
    """runtime._claude_client() 대체 — cassette 를 순서대로 재생."""

    def __init__(self, responses: list[dict]):
        self.messages = _Messages(responses)
