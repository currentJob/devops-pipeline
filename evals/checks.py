"""결정론 검증 — 라우팅 일치 + 도구 계약(must_call / forbidden)."""

from __future__ import annotations

from evals.trace import AgentTrace


def check(scenario: dict, trace: AgentTrace) -> list[str]:
    """시나리오 expect 대비 위반 목록 반환 (빈 리스트 = 통과)."""
    exp = scenario.get("expect", {})
    failures: list[str] = []

    if not trace.ok:
        failures.append("게이트웨이 실행이 실패(Outcome.ok=False)")

    expected_route = exp.get("route")
    if expected_route and trace.route != expected_route:
        failures.append(f"route 불일치: 기대 {expected_route}, 실제 {trace.route!r}")

    called = trace.called_tools
    for tool in exp.get("must_call", []):
        if tool not in called:
            failures.append(f"must_call 누락: {tool} (호출된 도구: {sorted(called)})")
    for tool in exp.get("forbidden", []):
        if tool in called:
            failures.append(f"forbidden 도구 호출됨: {tool}")

    return failures
