"""LangGraph 멀티 에이전트 게이트웨이.

Gateway(Router) 가 작업 유형을 분석하여 전문 에이전트로 분기:

  START → [retrieve] → [router] → code | doc | infra | stack | general → END

  Planner 는 별도 StateGraph 로 run_task 를 반복 호출:
  START → [plan] → [execute loop] → END
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from enum import StrEnum
from typing import Any
from uuid import UUID

import aiohttp
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks.base import AsyncCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent
from typing_extensions import TypedDict

from app import config
from app.agent.tools import (
    TOOLS,
    bash,
    read_file,
    recent_research,
    vault_save,
    vault_search,
    write_file,
)
from app.rag.retriever import retrieve_context
from app.worker import metrics, store

logger = logging.getLogger(__name__)

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

# ── 멀티 에이전트 상태 ────────────────────────────────────────────────────────


class _AgentState(TypedDict):
    task_id: str
    description: str  # 라우터가 prefix 제거 후 업데이트
    rag_context: str  # retrieve 노드가 채움
    route: str  # 라우터가 채움
    result: str  # 전문 에이전트가 채움


# ── 알림 & 콜백 ──────────────────────────────────────────────────────────────


async def _notify(text: str) -> None:
    """봇 /notify 엔드포인트로 중간 이벤트 전송 (실패해도 작업 계속)."""
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                config.WORKER_BOT_NOTIFY_URL,
                json={"text": text},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp,
        ):
            if resp.status != 200:
                logger.warning("중간 알림 비-200: %s", resp.status)
    except aiohttp.ClientError as e:
        logger.warning("중간 알림 실패: %s", e)


class _ToolNotifyHandler(AsyncCallbackHandler):
    """ReAct 루프에서 도구 호출 시 Telegram 알림."""

    def __init__(self, task_id: str) -> None:
        super().__init__()
        self.task_id = task_id
        self._step = 0

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._step += 1
        name = serialized.get("name", "unknown")
        await _notify(f"🔧 *{name}* (id=`{self.task_id}`, step {self._step})\n{input_str[:120]}")


# ── LLM 팩토리 ───────────────────────────────────────────────────────────────


_VLLM_HEALTH_TTL_S = 30.0
_vllm_health_cache: tuple[float, bool] | None = None  # (checked_at, healthy)


async def _vllm_available() -> bool:
    """vLLM /health 프로브. 결과를 짧게 캐시하고, 미설정/응답불가면 False."""
    if not config.VLLM_ENDPOINT:
        return False

    global _vllm_health_cache
    now = time.monotonic()
    if _vllm_health_cache and now - _vllm_health_cache[0] < _VLLM_HEALTH_TTL_S:
        return _vllm_health_cache[1]

    healthy = False
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                f"{config.VLLM_ENDPOINT}/health",
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp,
        ):
            healthy = resp.status == 200
    except (aiohttp.ClientError, TimeoutError) as e:
        logger.warning("vLLM 헬스체크 실패 → Claude API 폴백: %s", e)

    _vllm_health_cache = (now, healthy)
    return healthy


def _vllm_max_tokens() -> int:
    """vLLM 출력 토큰 상한 — 컨텍스트(max-model-len)의 절반으로 캡해 입력 공간 확보.

    출력+입력이 컨텍스트를 넘으면 vLLM 이 400 을 낸다. WORKER_MAX_TOKENS(=Claude용 8192)를
    vLLM 에 그대로 쓰면 작은 컨텍스트에서 초과하므로, 컨텍스트 절반으로 제한한다.
    """
    return min(config.WORKER_MAX_TOKENS, max(256, config.VLLM_MAX_MODEL_LEN // 2))


def _vllm_llm() -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url=f"{config.VLLM_ENDPOINT}/v1",
        api_key="token-placeholder",  # vLLM은 기본적으로 인증 불필요
        model=config.VLLM_MODEL,
        max_tokens=_vllm_max_tokens(),
        timeout=config.WORKER_TIMEOUT_S,
    )


def _claude_llm() -> BaseChatModel:
    return ChatAnthropic(
        model=config.WORKER_MODEL,
        api_key=config.CLAUDE_API_KEY,
        max_tokens=config.WORKER_MAX_TOKENS,
        timeout=config.WORKER_TIMEOUT_S,
    )


def _route_backend_label(route: str | None) -> str:
    """라우트에 매핑된 선호 백엔드 표시용 ('vLLM' | 'Claude')."""
    return "vLLM" if (route in config.VLLM_ROUTES_SET and config.VLLM_ENDPOINT) else "Claude"


async def _make_llm(route: str | None = None) -> BaseChatModel:
    """라우트별 백엔드 선택 + 가용성 폴백.

    VLLM_ROUTES 에 속한 라우트는 vLLM(가용 시), 그 외는 Claude.
    선호 백엔드가 불가하면 다른 쪽으로 폴백한다.
    """
    if route in config.VLLM_ROUTES_SET and await _vllm_available():
        logger.info("백엔드 선택 route=%s → vLLM", route)
        return _vllm_llm()
    if config.CLAUDE_API_KEY:
        logger.info("백엔드 선택 route=%s → Claude", route)
        return _claude_llm()
    if await _vllm_available():  # Claude 키 없음 — vLLM 으로라도
        logger.info("백엔드 선택 route=%s → vLLM (Claude 키 없음)", route)
        return _vllm_llm()
    return _claude_llm()


# ── 에이전트별 시스템 프롬프트 + 도구 셋 ─────────────────────────────────────

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


def _dated(prompt: str) -> str:
    return prompt + f"\n\n오늘 날짜: {datetime.date.today().strftime('%Y-%m-%d')}."


# 라우트별 (프롬프트, 도구) 매핑
_AGENT_CONFIG: dict[str, dict] = {
    Route.CODE: {"prompt": _CODE_PROMPT, "tools": [bash, read_file, write_file]},
    Route.DOC: {
        "prompt": _DOC_PROMPT,
        "tools": [read_file, write_file, recent_research, vault_search, vault_save],
    },
    Route.INFRA: {"prompt": _INFRA_PROMPT, "tools": [bash, read_file, write_file]},
    Route.STACK: {
        "prompt": _STACK_PROMPT,
        "tools": [recent_research, vault_search, vault_save],
    },
    Route.GENERAL: {"prompt": _GENERAL_PROMPT, "tools": TOOLS},
}


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
    llm = await _make_llm()
    resp = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "방금 완료된 작업을 다음 작업이 참조하도록 한국어 1~2문장으로 요약하라.\n"
                    "- 무엇을 했고 핵심 결과/결정/산출물(URL·파일·지적사항)만 남겨라.\n"
                    "- 인사말·군더더기 금지. 120자 이내."
                )
            ),
            HumanMessage(content=f"[요청]\n{description[:500]}\n\n[결과]\n{result[:1500]}"),
        ]
    )
    return resp.content.strip()[:300]


async def _run_react(task_id: str, description: str, rag_context: str, route: str) -> str:
    """지정 라우트의 전문 에이전트로 ReAct 루프 실행."""
    cfg = _AGENT_CONFIG[route]
    memory = await _recent_memory_block()
    parts: list[str] = []
    if memory:
        parts.append(memory)
    parts.append(description)
    if rag_context:
        parts.append(rag_context)
        parts.append("위 참고 문서를 기반으로 답변하세요.")
    augmented = "\n\n".join(parts)
    agent = create_react_agent(
        await _make_llm(route),
        cfg["tools"],
        prompt=SystemMessage(content=_dated(cfg["prompt"])),
    )
    # 라우트·백엔드별 사용량/지연 계측 (Grafana 대시보드용)
    metrics.ROUTE_TOTAL.labels(route=route, backend=_route_backend_label(route)).inc()
    with metrics.ROUTE_DURATION.labels(route=route).time():
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=augmented)]},
            config={
                "recursion_limit": config.WORKER_MAX_ITERATIONS * 2 + 2,
                "callbacks": [_ToolNotifyHandler(task_id)],
            },
        )
    last = result["messages"][-1]
    return last.content if hasattr(last, "content") else str(last)


# ── 게이트웨이 그래프 노드 ────────────────────────────────────────────────────


# 도구형 작업(로컬 파일/명령 분석)은 웹 검색이 노이즈·토큰 낭비라 RAG 생략
_NO_RAG_PREFIXES = ("[CODE_TASK]", "[INFRA_TASK]")


async def _retrieve_node(state: _AgentState) -> _AgentState:
    """RAG 웹 검색으로 컨텍스트 수집. 코드/인프라 도구 작업은 생략해 입력 절감."""
    description = state["description"]
    if description.startswith(_NO_RAG_PREFIXES):
        return {**state, "rag_context": ""}
    ctx = await retrieve_context(description)
    return {**state, "rag_context": ctx}


async def _router_node(state: _AgentState) -> _AgentState:
    """
    1순위: prefix 결정론적 분기 ([CODE_TASK] 등)
    2순위: LLM 분류 (자유형 요청)
    """
    description = state["description"]

    # 1. Prefix 결정론적 분기
    for prefix, route in _PREFIX_MAP.items():
        if description.startswith(prefix):
            cleaned = description[len(prefix) :].strip()
            logger.info("게이트웨이 prefix 분기 → %s (task_id=%s)", route.value, state["task_id"])
            await _notify(
                f"🔀 *게이트웨이* → `{route.value}` 에이전트 "
                f"[{_route_backend_label(route.value)}] (id=`{state['task_id']}`)"
            )
            return {**state, "description": cleaned, "route": route.value}

    # 2. LLM 분류 (자유형)
    llm = await _make_llm()
    resp = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "작업을 가장 적합한 카테고리 하나로 분류하세요. 카테고리 이름만 응답.\n"
                    "- code : 코드 분석·버그·리팩토링·보안\n"
                    "- doc  : 문서·README·API 문서·가이드\n"
                    "- infra: Docker·CI/CD·인프라·배포\n"
                    "- stack: IT 트렌드·기술 스택·Obsidian vault 저장\n"
                    "- general: 위 카테고리 외 일반 작업"
                )
            ),
            HumanMessage(content=description[:500]),
        ]
    )
    route_str = resp.content.strip().lower().split()[0]
    valid = {r.value for r in Route}
    route = route_str if route_str in valid else Route.GENERAL.value

    logger.info("게이트웨이 LLM 분류 → %s (task_id=%s)", route, state["task_id"])
    await _notify(
        f"🔀 *게이트웨이* → `{route}` 에이전트 "
        f"[{_route_backend_label(route)}] (id=`{state['task_id']}`)"
    )
    return {**state, "route": route}


def _dispatch(state: _AgentState) -> str:
    return state["route"]


def _make_agent_node(route: str):
    """라우트별 에이전트 노드 팩토리."""

    async def _node(state: _AgentState) -> _AgentState:
        result = await _run_react(
            state["task_id"], state["description"], state["rag_context"], route
        )
        return {**state, "result": result}

    _node.__name__ = f"_{route}_node"
    return _node


# ── 멀티 에이전트 게이트웨이 그래프 빌드 ────────────────────────────────────


def _build_gateway_graph():
    g = StateGraph(_AgentState)
    g.add_node("retrieve", _retrieve_node)
    g.add_node("router", _router_node)

    route_map: dict[str, str] = {}
    for route in Route:
        g.add_node(route.value, _make_agent_node(route.value))
        g.add_edge(route.value, END)
        route_map[route.value] = route.value

    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "router")
    g.add_conditional_edges("router", _dispatch, route_map)
    return g.compile()


_gateway = _build_gateway_graph()


# ── Planner StateGraph ────────────────────────────────────────────────────────


class _PlanState(TypedDict):
    task_id: str
    description: str
    sub_tasks: list[str]
    current_index: int
    results: list[str]


async def _plan_node(state: _PlanState) -> _PlanState:
    """복합 작업을 JSON 으로 하위 작업 목록으로 분해."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    llm = await _make_llm()
    resp = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "작업 분해 전문가입니다. 복합 작업을 독립 실행 가능한 하위 작업으로 분해하세요.\n"
                    f"오늘 날짜: {today}.\n"
                    '반드시 JSON만 응답: {"tasks": ["하위 작업1", "하위 작업2"]}\n'
                    "최대 5개. 각 하위 작업은 독립적으로 실행 가능해야 함."
                )
            ),
            HumanMessage(content=state["description"]),
        ]
    )
    try:
        sub_tasks: list[str] = json.loads(resp.content).get("tasks", [])
        if not sub_tasks:
            raise ValueError
        sub_tasks = [str(t) for t in sub_tasks[:5]]
    except (json.JSONDecodeError, ValueError, AttributeError):
        sub_tasks = [state["description"]]

    logger.info("플래너 분해 task_id=%s sub_tasks=%d개", state["task_id"], len(sub_tasks))
    await _notify(f"📋 *플래너* (id=`{state['task_id']}`)\n{len(sub_tasks)}개 하위 작업으로 분해")
    return {**state, "sub_tasks": sub_tasks, "current_index": 0, "results": []}


async def _execute_node(state: _PlanState) -> _PlanState:
    """현재 하위 작업을 게이트웨이(자동 라우팅)로 실행."""
    idx = state["current_index"]
    sub = state["sub_tasks"][idx]
    total = len(state["sub_tasks"])
    sub_id = f"{state['task_id']}-{idx + 1}"

    logger.info("플래너 실행 task_id=%s step=%d/%d", state["task_id"], idx + 1, total)
    await _notify(f"▶️ 하위 작업 {idx + 1}/{total} (id=`{sub_id}`)\n{sub[:100]}")

    # 게이트웨이를 통해 자동 라우팅 → 최적 에이전트 선택
    result = await run_task(sub_id, sub)
    entry = f"**[{idx + 1}/{total}] {sub[:60]}**\n{result}"
    return {**state, "current_index": idx + 1, "results": state["results"] + [entry]}


def _should_continue(state: _PlanState) -> str:
    return "execute" if state["current_index"] < len(state["sub_tasks"]) else END


def _build_plan_graph():
    g = StateGraph(_PlanState)
    g.add_node("plan", _plan_node)
    g.add_node("execute", _execute_node)
    g.add_edge(START, "plan")
    g.add_edge("plan", "execute")
    g.add_conditional_edges("execute", _should_continue, {"execute": "execute", END: END})
    return g.compile()


_plan_graph = _build_plan_graph()


# ── 공개 API ─────────────────────────────────────────────────────────────────


async def run_task(task_id: str, description: str) -> str:
    """게이트웨이를 통해 최적 전문 에이전트로 자동 라우팅."""
    if not config.CLAUDE_API_KEY and not config.VLLM_ENDPOINT:
        return "(LLM 백엔드 미설정 — .env 의 CLAUDE_API_KEY 또는 VLLM_ENDPOINT 추가 필요)"
    state = await _gateway.ainvoke(
        {
            "task_id": task_id,
            "description": description,
            "rag_context": "",
            "route": "",
            "result": "",
        }
    )
    return state["result"]


async def run_plan_task(task_id: str, description: str) -> str:
    """복합 작업을 하위 작업으로 분해 후 게이트웨이로 순차 실행."""
    if not config.CLAUDE_API_KEY and not config.VLLM_ENDPOINT:
        return "(LLM 백엔드 미설정 — CLAUDE_API_KEY 또는 VLLM_ENDPOINT 필요)"
    state = await _plan_graph.ainvoke(
        {
            "task_id": task_id,
            "description": description,
            "sub_tasks": [],
            "current_index": 0,
            "results": [],
        }
    )
    return "\n\n---\n\n".join(state["results"]) or "(결과 없음)"
