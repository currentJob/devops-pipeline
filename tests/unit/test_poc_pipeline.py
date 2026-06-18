"""PoC 자동 파이프라인(app.pipeline.poc_pipeline) 단위 테스트.

LangGraph 그래프의 분기·반복·종료를 검증한다 — pocsandbox HTTP·수정 에이전트·평가를
모두 모킹해 제어 흐름만 본다:
  - 빌드 실패 → 수정 → 재빌드 성공 → 평가 경로
  - max_iterations 도달 시 수정 중단하고 평가로 종료
  - 보안 정적검사 위반(stage=check)은 수정 없이 즉시 종료
  - pocfix 라우트가 read/write 만 노출(실행·네트워크 도구 비노출)
"""

from __future__ import annotations

from app import config
from app.pipeline import poc_pipeline


def _state(**kw) -> dict:
    base = {
        "slug": "p",
        "iteration": 0,
        "max_iterations": 3,
        "build_result": {},
        "fix_notes": [],
        "eval_result": None,
        "status": "x",
    }
    base.update(kw)
    return base


# ── after_build 분기 (순수 함수) ──────────────────────────────────────────────


def test_after_build_success_goes_evaluate():
    assert poc_pipeline.after_build(_state(build_result={"ok": True})) == "evaluate"


def test_after_build_fixable_failure_goes_fix():
    s = _state(build_result={"ok": False, "stage": "build"}, iteration=0, max_iterations=3)
    assert poc_pipeline.after_build(s) == "fix"


def test_after_build_security_violation_no_fix():
    # stage=check(정적검사 위반)는 수정 가능 단계가 아님 → 즉시 evaluate
    s = _state(build_result={"ok": False, "stage": "check"}, iteration=0, max_iterations=3)
    assert poc_pipeline.after_build(s) == "evaluate"


def test_after_build_exhausted_iterations_goes_evaluate():
    s = _state(build_result={"ok": False, "stage": "build"}, iteration=3, max_iterations=3)
    assert poc_pipeline.after_build(s) == "evaluate"


# ── 도구 노출 (보안 가드) ─────────────────────────────────────────────────────


def test_pocfix_route_is_read_write_only():
    from app.tools import ROUTE_TOOLS, tools_for

    assert set(ROUTE_TOOLS["pocfix"]) == {"read_file", "write_file"}
    anthropic, _ = tools_for("pocfix")
    assert {s["name"] for s in anthropic} == {"read_file", "write_file"}  # bash·network 비노출


# ── run_autopilot 통합 (모킹) ─────────────────────────────────────────────────


def _setup_mocks(tmp_path, monkeypatch, *, slug="sample"):
    """공통 모킹: WORKSPACE→tmp_path, PoC 디렉토리 생성, _notify·evaluate no-op."""
    monkeypatch.setattr(poc_pipeline.filesystem, "WORKSPACE", tmp_path)
    (tmp_path / "prompts" / "output" / "poc" / slug).mkdir(parents=True)

    async def noop_notify(*_a, **_k):
        pass

    monkeypatch.setattr(poc_pipeline.runtime, "_notify", noop_notify)

    captured: dict = {}

    async def fake_eval(_poc_dir, slug_arg, build_result):
        captured["build_result"] = build_result
        return {"slug": slug_arg, "overall": 4.0, "scores": {}, "summary": "ok", "report_path": "x"}

    monkeypatch.setattr(poc_pipeline.poc_eval, "evaluate", fake_eval)
    return captured


async def test_autopilot_fail_then_fix_then_success(tmp_path, monkeypatch):
    captured = _setup_mocks(tmp_path, monkeypatch)
    builds = [
        {"ok": False, "stage": "build", "logs": "err1"},
        {"ok": True, "stage": "run", "logs": "ok"},
    ]
    calls = {"sandbox": 0, "fix": 0}

    async def fake_sandbox(_slug):
        calls["sandbox"] += 1
        return builds.pop(0)

    async def fake_run_agent(route, _system, _user, _task_id):
        calls["fix"] += 1
        assert route == "pocfix"
        return "의존성 추가로 수정"

    monkeypatch.setattr(poc_pipeline, "_call_sandbox", fake_sandbox)
    monkeypatch.setattr(poc_pipeline.runtime, "run_agent", fake_run_agent)

    result = await poc_pipeline.run_autopilot("sample")
    assert result["ok"] is True
    assert result["build_ok"] is True
    assert calls["sandbox"] == 2  # 첫 빌드 실패 + 재빌드 성공
    assert calls["fix"] == 1  # 한 번 수정
    assert result["iterations"] == 1
    assert captured["build_result"]["ok"] is True  # 평가는 최종(성공) 빌드 결과로 수행


async def test_autopilot_exhausts_iterations(tmp_path, monkeypatch):
    _setup_mocks(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "POC_AUTOPILOT_MAX_ITERATIONS", 2)
    fix = {"n": 0}

    async def always_fail(_slug):
        return {"ok": False, "stage": "build", "logs": "e"}

    async def fake_fix(*_a):
        fix["n"] += 1
        return "tried"

    monkeypatch.setattr(poc_pipeline, "_call_sandbox", always_fail)
    monkeypatch.setattr(poc_pipeline.runtime, "run_agent", fake_fix)

    result = await poc_pipeline.run_autopilot("sample")
    assert result["build_ok"] is False
    assert fix["n"] == 2  # max_iterations=2 → 2회 수정 시도 후 평가로 종료
    assert result["iterations"] == 2


async def test_autopilot_security_violation_no_fix(tmp_path, monkeypatch):
    _setup_mocks(tmp_path, monkeypatch)
    fix = {"n": 0}

    async def check_fail(_slug):
        return {"ok": False, "stage": "check", "logs": "privileged 금지"}

    async def fake_fix(*_a):
        fix["n"] += 1
        return "x"

    monkeypatch.setattr(poc_pipeline, "_call_sandbox", check_fail)
    monkeypatch.setattr(poc_pipeline.runtime, "run_agent", fake_fix)

    result = await poc_pipeline.run_autopilot("sample")
    assert result["build_ok"] is False
    assert fix["n"] == 0  # 보안위반은 자동 수정 시도 자체를 안 함


async def test_autopilot_invalid_slug():
    result = await poc_pipeline.run_autopilot("../etc")
    assert result["ok"] is False


async def test_autopilot_missing_poc(tmp_path, monkeypatch):
    monkeypatch.setattr(poc_pipeline.filesystem, "WORKSPACE", tmp_path)
    result = await poc_pipeline.run_autopilot("nope")
    assert result["ok"] is False and "없음" in result["detail"]
