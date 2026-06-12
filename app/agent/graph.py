"""멀티 에이전트 게이트웨이 (네이티브 — LangChain/LangGraph 없음).

평범한 async 오케스트레이션:
  run_task:      retrieve(RAG) → route(분기) → run_agent(도구 루프)
  run_plan_task: plan(분해) → 하위 작업마다 run_task 순차 실행

LLM 호출은 app.agent.runtime (anthropic/openai 직접) 으로 위임한다.
"""

from __future__ import annotations

import datetime
import json
import logging
from enum import StrEnum

from app import config
from app.agent import runtime
from app.agent.outcome import Outcome
from app.agent.runtime import _notify, _route_backend_label  # 재노출 (worker/agent.py 호환)
from app.rag.retriever import retrieve_context
from app.worker import metrics, store

logger = logging.getLogger(__name__)

__all__ = ["Outcome", "_notify", "run_task", "run_plan_task", "summarize_task"]

# ── 라우트 정의 ───────────────────────────────────────────────────────────────


class Route(StrEnum):
    CODE = "code"
    DOC = "doc"
    INFRA = "infra"
    STACK = "stack"
    GENERAL = "general"


# Telegram 봇 커맨드(/code, /doc …)가 삽입하는 prefix → 결정론적 라우팅
_PREFIX_MAP: dict[str, Route] = {
    "[CODE_TASK]": Route.CODE,
    "[DOC_TASK]": Route.DOC,
    "[INFRA_TASK]": Route.INFRA,
    "[STACK_TASK]": Route.STACK,
}

# ── 에이전트별 시스템 프롬프트 (도구 셋은 app.tools.ROUTE_TOOLS 가 관리) ──────────

# vault_save 로 노트를 남기는 라우트(doc/stack/general)에 공통 적용되는 Obsidian 작성 양식.
_VAULT_NOTE_FORMAT = """
[vault_save 노트 양식 — Obsidian]
vault_save 의 content 는 아래 Obsidian 양식을 따른다:
- 맨 위에 `> [!summary] TL;DR` 콜아웃으로 핵심 결론 2-3줄
- `##` 제목으로 구조화하고, 핵심은 `> [!tip]`·주의/한계는 `> [!warning]` 콜아웃으로 강조
- vault_search 로 찾은 관련 기존 노트는 `## 관련 노트` 섹션에 `[[노트제목]]` 위키링크로 연결
- 후속 작업·검증 항목이 있으면 `- [ ]` 체크박스로 정리
- 출처가 있으면 `## 출처` 에 `[제목](url)` 링크로 명시
- tags 인자: 계층형 중첩 태그를 쉼표로 (예: `type/research, area/vector-db, tech/qdrant`)
- aliases 인자: 동의어·약어가 있으면 쉼표로 (선택)"""

_CODE_PROMPT = """당신은 코드 품질 분석 전문 에이전트입니다.
도구: read_file, write_file, bash

- 버그·보안 취약점·성능 이슈 탐지 (파일:라인 형식으로 지목)
- 리팩토링 제안 (Before/After 코드 블록 포함)
- 수정 제안은 prompts/output/ 에 write_file 로 저장."""

_DOC_PROMPT = """당신은 기술 문서 작성 전문 에이전트입니다.
도구: read_file, write_file, recent_research, vault_search, vault_save

- README·API 문서·아키텍처 설명·온보딩 가이드 작성
- read_file 로 코드 확인 후 한국어로 문서화
- 최신 동향·버전·생태계 현황이 필요하면 recent_research 로 최근 자료를 먼저 수집해 반영
- 지식 노트로 남길 결과물은 vault_save 로 Obsidian vault 에 저장
  (category=분류 폴더, tags=쉼표 구분). 단순 산출물은 write_file 사용."""

_INFRA_PROMPT = """당신은 인프라/DevOps 전문 에이전트입니다.
도구: bash, read_file, write_file

- Docker·docker-compose·CI/CD 설정 분석 및 최적화
- bash / read_file 로 실제 설정 확인 후 분석
- 변경 권고는 write_file 로 prompts/output/ 에 저장하고 사용자가 직접 적용하도록 안내."""

_STACK_PROMPT = """당신은 IT 트렌드 리서치 전문 에이전트입니다.
도구: recent_research, vault_search, vault_save

- vault_search 로 기존 노트를 확인하여 중복 방지
- 트렌드 선정 전 recent_research 로 최근 한 달간 실제 커뮤니티 반응·채택 신호를 수집하라.
  학습 지식만으로 추측하지 말고, 조사 결과의 출처를 근거로 현재 시점 채택률·성숙도를 작성.
- vault_save 는 **정확히 한 번만** 호출하라. 성공 응답("저장 완료: <경로>")을 받으면
  즉시 그 경로만 응답하고, 추가 도구 호출을 절대 하지 마라 (중복 노트 생성 금지)."""

_GENERAL_PROMPT = """당신은 DevOps/IaC 자동화 어시스턴트입니다.
도구: read_file, write_file, bash, recent_research, vault_search, vault_save

- 추측 금지 — 도구로 사실 확인 후 응답
- 시점에 민감하거나(최신 동향·요즘·최근) 학습 지식으로 답하기 어려운 주제는
  recent_research 로 최근 한 달 자료를 조사한 뒤 출처와 함께 답하라
- 지식/트렌드로 남길 만한 결과는 vault_save 로 Obsidian vault 에 저장
- 코드 변경이 필요하면 prompts/output/ 에 권고 문서 작성 후 수동 적용 안내
- [참고 문서] 블록이 제공된 경우 최우선 근거로 활용"""

# doc/stack/general 은 vault_save 로 노트를 남기므로 Obsidian 작성 양식을 덧붙인다.
_ROUTE_PROMPT: dict[str, str] = {
    Route.CODE: _CODE_PROMPT,
    Route.DOC: _DOC_PROMPT + _VAULT_NOTE_FORMAT,
    Route.INFRA: _INFRA_PROMPT,
    Route.STACK: _STACK_PROMPT + _VAULT_NOTE_FORMAT,
    Route.GENERAL: _GENERAL_PROMPT + _VAULT_NOTE_FORMAT,
}


def _dated(prompt: str) -> str:
    return prompt + f"\n\n오늘 날짜: {datetime.date.today().strftime('%Y-%m-%d')}."


# ── 메모리 ────────────────────────────────────────────────────────────────────


async def _recent_memory_block() -> str:
    """직전 작업 요약본 N개를 컨텍스트 블록으로 구성 (조회 실패해도 빈 문자열)."""
    if config.WORKER_MEMORY_COUNT <= 0:
        return ""
    try:
        rows = await store.get_recent_summaries(config.WORKER_MEMORY_COUNT)
    except Exception as e:  # DB 미초기화 등 — 메모리는 부가기능이므로 무시
        logger.warning("이전 작업 메모리 조회 실패: %s", e)
        return ""
    if not rows:
        return ""
    lines = [f"- ({r['created_at']}) {r['summary']}" for r in rows]
    return (
        "[이전 작업 메모리] 직전 작업 요약입니다. 관련 있으면 참고하되, "
        "무관하면 무시하라.\n" + "\n".join(lines)
    )


async def summarize_task(description: str, result: str) -> str:
    """완료된 작업을 다음 요청이 참조할 1~2문장 요약으로 압축."""
    summary = await runtime.chat(
        system=(
            "방금 완료된 작업을 다음 작업이 참조하도록 한국어 1~2문장으로 요약하라.\n"
            "- 무엇을 했고 핵심 결과/결정/산출물(URL·파일·지적사항)만 남겨라.\n"
            "- 인사말·군더더기 금지. 120자 이내."
        ),
        user=f"[요청]\n{description[:500]}\n\n[결과]\n{result[:1500]}",
    )
    return summary.strip()[:300]


# ── 게이트웨이: retrieve → route → run_agent ─────────────────────────────────

# 도구형 작업(로컬 파일/명령 분석)은 웹 검색이 노이즈·토큰 낭비라 RAG 생략
_NO_RAG_PREFIXES = ("[CODE_TASK]", "[INFRA_TASK]")


async def _retrieve(description: str) -> str:
    """RAG 웹 검색으로 컨텍스트 수집. 코드/인프라 도구 작업은 생략해 입력 절감."""
    if description.startswith(_NO_RAG_PREFIXES):
        return ""
    return await retrieve_context(description)


async def _route(task_id: str, description: str) -> tuple[str, str]:
    """작업 분기. 반환: (route, cleaned_description).

    1순위: prefix 결정론적 분기 ([CODE_TASK] 등)
    2순위: LLM 분류 (자유형 요청)
    """
    for prefix, route in _PREFIX_MAP.items():
        if description.startswith(prefix):
            cleaned = description[len(prefix) :].strip()
            logger.info("게이트웨이 prefix 분기 → %s (task_id=%s)", route.value, task_id)
            await _notify(
                f"🔀 *게이트웨이* → `{route.value}` 에이전트 "
                f"[{_route_backend_label(route.value)}] (id=`{task_id}`)"
            )
            return route.value, cleaned

    classification = await runtime.chat(
        system=(
            "작업을 가장 적합한 카테고리 하나로 분류하세요. 카테고리 이름만 응답.\n"
            "- code : 코드 분석·버그·리팩토링·보안\n"
            "- doc  : 문서·README·API 문서·가이드\n"
            "- infra: Docker·CI/CD·인프라·배포\n"
            "- stack: IT 트렌드·기술 스택·Obsidian vault 저장\n"
            "- general: 위 카테고리 외 일반 작업"
        ),
        user=description[:500],
    )
    route_str = classification.strip().lower().split()[0] if classification.strip() else ""
    valid = {r.value for r in Route}
    route = route_str if route_str in valid else Route.GENERAL.value

    logger.info("게이트웨이 LLM 분류 → %s (task_id=%s)", route, task_id)
    await _notify(
        f"🔀 *게이트웨이* → `{route}` 에이전트 [{_route_backend_label(route)}] (id=`{task_id}`)"
    )
    return route, description


def _augment(description: str, memory: str, rag_context: str) -> str:
    parts: list[str] = []
    if memory:
        parts.append(memory)
    parts.append(description)
    if rag_context:
        parts.append(rag_context)
        parts.append("위 참고 문서를 기반으로 답변하세요.")
    return "\n\n".join(parts)


# ── 공개 API ─────────────────────────────────────────────────────────────────


async def run_task(task_id: str, description: str) -> Outcome:
    """게이트웨이를 통해 최적 전문 에이전트로 자동 라우팅."""
    if not config.CLAUDE_API_KEY and not config.VLLM_ENDPOINT:
        return Outcome.failure(
            "LLM 백엔드 미설정 — .env 의 CLAUDE_API_KEY 또는 VLLM_ENDPOINT 추가 필요"
        )

    rag_context = await _retrieve(description)
    route, cleaned = await _route(task_id, description)
    memory = await _recent_memory_block()
    augmented = _augment(cleaned, memory, rag_context)

    # 라우트·백엔드별 사용량/지연 계측 (Grafana 대시보드용)
    metrics.ROUTE_TOTAL.labels(route=route, backend=_route_backend_label(route)).inc()
    with metrics.ROUTE_DURATION.labels(route=route).time():
        text = await runtime.run_agent(route, _dated(_ROUTE_PROMPT[route]), augmented, task_id)
    return Outcome.success(text)


async def _plan(task_id: str, description: str) -> list[str]:
    """복합 작업을 하위 작업 목록으로 분해 (실패 시 원본 단일 작업)."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    raw = await runtime.chat(
        system=(
            "작업 분해 전문가입니다. 복합 작업을 독립 실행 가능한 하위 작업으로 분해하세요.\n"
            f"오늘 날짜: {today}.\n"
            '반드시 JSON만 응답: {"tasks": ["하위 작업1", "하위 작업2"]}\n'
            "최대 5개. 각 하위 작업은 독립적으로 실행 가능해야 함."
        ),
        user=description,
    )
    try:
        sub_tasks = json.loads(raw).get("tasks", [])
        if not sub_tasks:
            raise ValueError
        sub_tasks = [str(t) for t in sub_tasks[:5]]
    except (json.JSONDecodeError, ValueError, AttributeError):
        sub_tasks = [description]

    logger.info("플래너 분해 task_id=%s sub_tasks=%d개", task_id, len(sub_tasks))
    await _notify(f"📋 *플래너* (id=`{task_id}`)\n{len(sub_tasks)}개 하위 작업으로 분해")
    return sub_tasks


async def run_plan_task(task_id: str, description: str) -> Outcome:
    """복합 작업을 하위 작업으로 분해 후 게이트웨이로 순차 실행."""
    if not config.CLAUDE_API_KEY and not config.VLLM_ENDPOINT:
        return Outcome.failure("LLM 백엔드 미설정 — CLAUDE_API_KEY 또는 VLLM_ENDPOINT 필요")

    sub_tasks = await _plan(task_id, description)
    total = len(sub_tasks)
    outcomes: list[Outcome] = []
    results: list[str] = []
    for idx, sub in enumerate(sub_tasks):
        sub_id = f"{task_id}-{idx + 1}"
        logger.info("플래너 실행 task_id=%s step=%d/%d", task_id, idx + 1, total)
        await _notify(f"▶️ 하위 작업 {idx + 1}/{total} (id=`{sub_id}`)\n{sub[:100]}")
        outcome = await run_task(sub_id, sub)
        outcomes.append(outcome)
        results.append(f"**[{idx + 1}/{total}] {sub[:60]}**\n{outcome.text}")

    combined = "\n\n---\n\n".join(results)
    if not combined:
        return Outcome.failure("결과 없음")
    # 하위 작업이 하나라도 실패하면 플랜 전체를 실패로 표기
    return Outcome(ok=all(o.ok for o in outcomes), text=combined)
