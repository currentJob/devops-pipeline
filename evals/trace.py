"""에이전트 1회 실행에서 수집하는 관측 결과."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentTrace:
    """게이트웨이 1회 실행 trace — 라우팅·도구 호출·최종 출력."""

    route: str = ""
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    output: str = ""
    ok: bool = True

    @property
    def called_tools(self) -> set[str]:
        return {name for name, _ in self.tool_calls}
