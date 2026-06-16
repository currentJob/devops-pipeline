"""eval 용 부작용 차단 스텁 — 도구 실행 기록 + 봇 알림 no-op.

실제 bash/write_file/vault_save 를 절대 실행하지 않고, 시나리오가 준 canned 출력을 돌려준다.
"""

from __future__ import annotations


async def noop_notify(*_args, **_kwargs) -> None:
    """봇 /notify 호출 차단 (eval 환경엔 봇이 없음)."""
    return None


async def empty_str(*_args, **_kwargs) -> str:
    """RAG·메모리 등 부가 컨텍스트 차단."""
    return ""


class ToolRecorder:
    """tools.execute 대체 — 호출 (name,args) 를 기록하고 canned 출력을 반환."""

    def __init__(self, tool_outputs: dict[str, str] | None = None):
        self._outputs = tool_outputs or {}
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, name: str, args: dict) -> str:
        self.calls.append((name, dict(args)))
        return self._outputs.get(name, f"(stub 출력: {name})")
