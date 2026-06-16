"""에이전트 라우팅·도구 계약 결정론 회귀 — 재생(cassette) 모드, 실 LLM 호출 0.

evals/scenarios/*.json 을 재생해 route 일치 + must_call/forbidden 도구 계약을 검증한다.
프롬프트(graph._ROUTE_PROMPT)·라우팅·도구 배선 회귀를 일반 CI 에서 무과금으로 잡는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals import checks, harness

_SCEN_DIR = Path(__file__).resolve().parents[2] / "evals" / "scenarios"
_SCENARIOS = sorted(_SCEN_DIR.glob("*.json"))


def test_scenarios_exist():
    assert _SCENARIOS, "evals/scenarios 에 시나리오 JSON 이 없음"


@pytest.mark.parametrize("path", _SCENARIOS, ids=lambda p: p.stem)
async def test_scenario_deterministic(path: Path):
    scenario = json.loads(path.read_text(encoding="utf-8"))
    trace = await harness.run_scenario(scenario)
    failures = checks.check(scenario, trace)
    assert not failures, f"{path.stem}: " + "; ".join(failures)
