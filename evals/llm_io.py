"""녹화/재생 LLM — Claude(AsyncAnthropic) 클라이언트의 가짜 구현.

runtime._claude_client() 를 이 ReplayClient 로 패치하면, runtime.chat / _run_claude 가
실제 API 대신 cassette(녹화된 응답 리스트)를 호출 순서대로 돌려받는다:
  - chat(라우팅 분류·요약)  → client.messages.create
  - 도구 루프(Agent SDK)     → client.beta.messages.tool_runner (가짜 runner 로 재생)
두 경로가 단일 cassette 커서를 공유한다(녹화 순서 = 분류 → 도구 턴들).

응답 객체는 anthropic Messages API 의 shape(.content[*].type/.text/.name/.input/.id,
.stop_reason)를 모사한다. vLLM 경로는 select_backend='claude' 고정으로 미사용.
"""

from __future__ import annotations

from app import tools


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


class _Cursor:
    """cassette 를 순서대로 소비하는 공유 커서 (chat 과 도구 루프가 함께 사용)."""

    def __init__(self, responses: list[dict]):
        self._responses = responses
        self._i = 0

    def next(self) -> _Response:
        if self._i >= len(self._responses):
            raise AssertionError(
                f"cassette 소진 — 녹화 응답 {len(self._responses)}개보다 LLM 호출이 많음. "
                "cassette('llm')를 보강하거나 record 로 재녹화하세요."
            )
        resp = self._responses[self._i]
        self._i += 1
        return _Response(resp)


class _ReplayToolRunner:
    """client.beta.messages.tool_runner 대체 — cassette 를 도구 루프처럼 재생.

    각 모델 턴을 yield 하고, tool_use 블록이 있으면 tools.execute(스텁으로 패치됨)를 호출해
    부작용 차단 + 호출 기록을 수행한다. end_turn(도구 없음) 턴을 yield 하면 종료.
    """

    def __init__(self, cursor: _Cursor):
        self._cursor = cursor

    async def __aiter__(self):
        while True:
            message = self._cursor.next()
            yield message
            tool_uses = [b for b in message.content if b.type == "tool_use"]
            if not tool_uses:
                return
            for b in tool_uses:
                await tools.execute(b.name, dict(b.input))


class _Messages:
    def __init__(self, cursor: _Cursor):
        self._cursor = cursor

    async def create(self, **_kwargs) -> _Response:
        return self._cursor.next()


class _BetaMessages:
    def __init__(self, cursor: _Cursor):
        self._cursor = cursor

    def tool_runner(self, **_kwargs) -> _ReplayToolRunner:
        return _ReplayToolRunner(self._cursor)


class _Beta:
    def __init__(self, cursor: _Cursor):
        self.messages = _BetaMessages(cursor)


class ReplayClient:
    """runtime._claude_client() 대체 — cassette 를 순서대로 재생 (chat + 도구 루프 공유)."""

    def __init__(self, responses: list[dict]):
        cursor = _Cursor(responses)
        self.messages = _Messages(cursor)
        self.beta = _Beta(cursor)
