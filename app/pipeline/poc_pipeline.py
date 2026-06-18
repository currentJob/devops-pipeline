"""PoC 자동 파이프라인 — LangGraph StateGraph (빌드↔수정 루프 → 평가).

bot /pocrun 확인 후 worker /poc/autopilot 이 1회 호출한다. 제어 흐름만 LangGraph 로
오케스트레이션하고, 실제 작업은 기존 자산을 재사용한다:
  - 빌드: pocsandbox(/run) 반복 호출 (정적검사·무-egress·자원캡·teardown 불변)
  - 수정: app.agent.runtime.run_agent("pocfix") — prompts/output/poc/<slug>/ 한정 편집
  - 평가: app.pipeline.poc_eval.evaluate — EVALUATION.md 생성
LLM 호출은 모두 runtime 경유 → 이중 백엔드(Claude/vLLM) 폴백 유지.

⚠️ LLM 생성 코드를 최대 N회까지 자동 격리 실행/수정한다. 휴먼게이트는 bot /pocrun 확인 1회.
보안 정적검사 위반(stage=check)은 자동수정하지 않고 즉시 종료한다(우회 시도 차단).
"""

from __future__ import annotations

import logging
from typing import TypedDict

import aiohttp
from langgraph.graph import END, StateGraph

from app import config
from app.agent import runtime
from app.pipeline import poc_eval
from app.tools import filesystem

logger = logging.getLogger(__name__)

# 코드 수정으로 고칠 수 있는 실패 단계. check(보안 정적검사 위반)/config/slug 는 수정 금지.
_FIXABLE_STAGES = frozenset({"build", "run"})
_SANDBOX_TIMEOUT_S = 600  # build(≤300s)+run(≤60s)+teardown 여유
_FIX_LOG_MAX = 3000  # 수정 에이전트에 전달할 빌드 로그 상한


class PocState(TypedDict):
    slug: str
    iteration: int
    max_iterations: int
    build_result: dict
    fix_notes: list[str]
    eval_result: dict | None
    status: str


def _poc_dir(slug: str):
    return (filesystem.WORKSPACE / poc_eval.POC_OUTPUT_SUBDIR / slug).resolve()


async def _call_sandbox(slug: str) -> dict:
    """pocsandbox /run 호출 → {ok, stage, logs}. 통신 실패도 동일 형태로 정규화."""
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                config.POCSANDBOX_RUN_URL,
                json={"slug": slug},
                timeout=aiohttp.ClientTimeout(total=_SANDBOX_TIMEOUT_S),
            ) as resp,
        ):
            return await resp.json()
    except aiohttp.ClientError as e:
        logger.warning("pocsandbox 통신 실패 slug=%s: %s", slug, e)
        return {"ok": False, "stage": "sandbox", "logs": f"샌드박스 연결 실패: {e}"}


# ── 노드 ──────────────────────────────────────────────────────────────────────


async def build_node(state: PocState) -> dict:
    slug, n, cap = state["slug"], state["iteration"], state["max_iterations"]
    await runtime._notify(f"🔨 *PoC 빌드* `{slug}` (시도 {n + 1}/{cap + 1})")
    result = await _call_sandbox(slug)
    icon = "✅" if result.get("ok") else "🔴"
    await runtime._notify(f"{icon} 빌드 결과 `{slug}` — stage: {result.get('stage', '?')}")
    return {"build_result": result, "status": "built"}


async def fix_node(state: PocState) -> dict:
    slug, n = state["slug"], state["iteration"]
    build = state["build_result"]
    stage = build.get("stage", "?")
    logs = (build.get("logs") or "")[:_FIX_LOG_MAX]
    await runtime._notify(f"🛠️ *PoC 수정* `{slug}` (반복 {n + 1}) — {stage} 단계 오류 수정")

    system = (
        "당신은 빌드에 실패한 PoC 프로젝트를 고치는 코드 수정 전문 에이전트입니다.\n"
        f"도구: read_file, write_file (쓰기는 prompts/output/poc/{slug}/ 하위만 허용).\n\n"
        "- 빌드 오류 로그를 분석해 원인을 파악하라.\n"
        "- read_file 로 관련 소스·Dockerfile·docker-compose.yml 을 확인한 뒤 write_file 로 최소 수정하라.\n"
        "- docker-compose 보안 설정(privileged·host bind·docker.sock·network_mode 등)을 절대 추가/변경하지 마라.\n"
        "- 네트워크 의존 우회(외부 호스트 하드코딩 등) 금지. 빌드가 통과하도록 코드·의존성만 고쳐라.\n"
        "- 마지막에 무엇을 왜 고쳤는지 1~2문장으로 요약하라."
    )
    user = (
        f"PoC slug: {slug}\n실패 단계: {stage}\n\n"
        f"[빌드 오류 로그]\n{logs}\n\n"
        f"prompts/output/poc/{slug}/ 의 소스를 읽고 빌드 오류를 고치세요."
    )
    try:
        note = await runtime.run_agent("pocfix", system, user, f"pocfix-{slug}-{n + 1}")
    except Exception as e:  # noqa: BLE001 — 수정 실패해도 다음 빌드/종료로 진행
        logger.warning("PoC 수정 에이전트 오류 slug=%s: %s", slug, e)
        note = f"(수정 에이전트 오류: {e})"

    notes = state["fix_notes"] + [f"[반복 {n + 1}] {note.strip()[:300]}"]
    return {"iteration": n + 1, "fix_notes": notes, "status": "fixed"}


async def evaluate_node(state: PocState) -> dict:
    slug = state["slug"]
    poc_dir = _poc_dir(slug)
    await runtime._notify(f"🧪 *PoC 평가* `{slug}` — EVALUATION.md 생성 중")
    result = await poc_eval.evaluate(poc_dir, slug, state["build_result"])

    # 자동 수정 이력을 리포트 끝에 덧붙인다(반복 횟수·수정 요약).
    if state["fix_notes"]:
        history = "\n".join(f"- {ln}" for ln in state["fix_notes"])
        report_path = poc_dir / poc_eval.REPORT_NAME
        try:
            existing = report_path.read_text(encoding="utf-8")
            report_path.write_text(
                existing + f"\n## 자동 수정 이력\n\n{history}\n", encoding="utf-8"
            )
        except OSError as e:
            logger.warning("자동 수정 이력 추가 실패 slug=%s: %s", slug, e)
    return {"eval_result": result, "status": "done"}


# ── 라우팅 ────────────────────────────────────────────────────────────────────


def after_build(state: PocState) -> str:
    """빌드 결과 분기. 성공/수정불가/반복소진 → evaluate, 수정가능+여유 → fix."""
    build = state["build_result"]
    if build.get("ok"):
        return "evaluate"
    stage = build.get("stage", "")
    if stage in _FIXABLE_STAGES and state["iteration"] < state["max_iterations"]:
        return "fix"
    # 보안위반(check)·구조오류(config/slug/sandbox)·반복 소진 → 미통과로 평가/종료
    return "evaluate"


def _build_graph():
    g = StateGraph(PocState)
    g.add_node("build", build_node)
    g.add_node("fix", fix_node)
    g.add_node("evaluate", evaluate_node)
    g.set_entry_point("build")
    g.add_conditional_edges("build", after_build, {"fix": "fix", "evaluate": "evaluate"})
    g.add_edge("fix", "build")
    g.add_edge("evaluate", END)
    return g.compile()


_GRAPH = _build_graph()


# ── 공개 진입점 (worker /poc/autopilot 이 호출) ───────────────────────────────


async def run_autopilot(slug: str, max_iterations: int | None = None) -> dict:
    """PoC 자동 빌드→수정→재빌드→평가 파이프라인 실행. 결과 요약 dict 반환."""
    if not poc_eval.valid_slug(slug):
        return {"ok": False, "detail": f"잘못된 slug: {slug!r}"}

    base = (filesystem.WORKSPACE / poc_eval.POC_OUTPUT_SUBDIR).resolve()
    poc_dir = _poc_dir(slug)
    if not str(poc_dir).startswith(str(base)) or not poc_dir.is_dir():
        return {"ok": False, "detail": f"PoC 없음: {slug}"}

    max_iter = (
        config.POC_AUTOPILOT_MAX_ITERATIONS if max_iterations is None else int(max_iterations)
    )
    max_iter = max(0, max_iter)

    initial: PocState = {
        "slug": slug,
        "iteration": 0,
        "max_iterations": max_iter,
        "build_result": {},
        "fix_notes": [],
        "eval_result": None,
        "status": "start",
    }
    # 최악의 경로(build→fix 반복)도 도달 가능하도록 재귀 한도를 반복 횟수에 맞춰 넉넉히.
    final = await _GRAPH.ainvoke(initial, {"recursion_limit": 2 * max_iter + 10})

    build = final.get("build_result") or {}
    return {
        "ok": True,
        "slug": slug,
        "build_ok": bool(build.get("ok")),
        "build_stage": build.get("stage"),
        "iterations": final.get("iteration", 0),
        "fix_notes": final.get("fix_notes", []),
        "eval": final.get("eval_result") or {},
    }
