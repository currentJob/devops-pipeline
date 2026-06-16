"""LLM-as-judge 품질 채점 — 라이브 모드에서만 호출 (실 LLM·과금).

시나리오 judge.rubric 기준으로 에이전트 출력을 0~5 로 채점한다.
"""

from __future__ import annotations

import json

from app.agent import runtime
from evals.trace import AgentTrace

_JUDGE_SYSTEM = """당신은 AI 에이전트 출력 품질 평가자입니다.
주어진 [요청]·[평가기준]·[에이전트 출력]을 보고 0~5 정수로 채점하세요.
- 5: 기준을 완전히 충족, 0: 전혀 충족 못 함
반드시 JSON만 출력: {"score": <0-5 정수>, "reason": "<채점 근거 한 문장>"}"""


async def judge(scenario: dict, trace: AgentTrace) -> dict:
    """judge 스펙이 있으면 채점 결과 dict, 없으면 {'skipped': True}."""
    spec = scenario.get("judge")
    if not spec:
        return {"skipped": True}

    user = (
        f"[요청]\n{scenario['input']}\n\n"
        f"[평가기준]\n{spec['rubric']}\n\n"
        f"[에이전트 출력]\n{trace.output[:2000]}"
    )
    raw = await runtime.chat(system=_JUDGE_SYSTEM, user=user)
    try:
        data = json.loads(raw)
        score = int(data.get("score", 0))
        reason = str(data.get("reason", ""))
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        score, reason = 0, f"채점 응답 파싱 실패: {raw[:120]}"

    threshold = int(spec.get("threshold", 3))
    return {
        "skipped": False,
        "score": score,
        "threshold": threshold,
        "passed": score >= threshold,
        "reason": reason,
    }
