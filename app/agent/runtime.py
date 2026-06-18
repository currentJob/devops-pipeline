"""LLM 런타임 — 백엔드 선택 + 단순 완성(chat) + 도구 사용 루프(run_agent).

Claude 경로는 Anthropic Agent SDK 의 도구 실행 루프(client.beta.messages.tool_runner +
app.agent.sdk_tools 의 @beta_async_tool 도구)를 사용한다. vLLM 경로는 openai 호환
chat.completions 로 도구 루프를 직접 구동한다. 두 경로 모두 실제 도구 실행은 app.tools 의
단일 레지스트리(execute)를 재사용해 권한 가드/트림을 공유한다.
"""

from __future__ import annotations

import json
import logging
import time

import aiohttp

from app import config
from app.agent import sdk_tools
from app.tools import execute, tools_for

logger = logging.getLogger(__name__)

# ── 알림 (봇 /notify 로 중간 이벤트) ──────────────────────────────────────────


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


# ── 백엔드 선택 + 가용성 폴백 ─────────────────────────────────────────────────

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
    """vLLM 출력 토큰 상한 — 컨텍스트(max-model-len)의 절반으로 캡해 입력 공간 확보."""
    return min(config.WORKER_MAX_TOKENS, max(256, config.VLLM_MAX_MODEL_LEN // 2))


def _route_backend_label(route: str | None) -> str:
    """라우트에 매핑된 선호 백엔드 표시용 ('vLLM' | 'Claude')."""
    return "vLLM" if (route in config.VLLM_ROUTES_SET and config.VLLM_ENDPOINT) else "Claude"


async def select_backend(route: str | None = None) -> str:
    """라우트별 백엔드 선택 + 가용성 폴백. 반환: 'vllm' | 'claude'."""
    if route in config.VLLM_ROUTES_SET and await _vllm_available():
        logger.info("백엔드 선택 route=%s → vLLM", route)
        return "vllm"
    if config.CLAUDE_API_KEY:
        logger.info("백엔드 선택 route=%s → Claude", route)
        return "claude"
    if await _vllm_available():  # Claude 키 없음 — vLLM 으로라도
        logger.info("백엔드 선택 route=%s → vLLM (Claude 키 없음)", route)
        return "vllm"
    return "claude"


def _claude_client():
    import anthropic

    return anthropic.AsyncAnthropic(api_key=config.CLAUDE_API_KEY, timeout=config.WORKER_TIMEOUT_S)


def _vllm_client():
    import openai

    return openai.AsyncOpenAI(
        base_url=f"{config.VLLM_ENDPOINT}/v1",
        api_key="token-placeholder",  # vLLM 은 기본적으로 인증 불필요
        timeout=config.WORKER_TIMEOUT_S,
    )


# ── 단순 완성 (도구 없음) ─────────────────────────────────────────────────────


async def chat(system: str, user: str, route: str | None = None) -> str:
    """단일 턴 완성 — 분류/요약/분해/커밋 메시지 등. 백엔드 자동 선택."""
    if await select_backend(route) == "vllm":
        client = _vllm_client()
        resp = await client.chat.completions.create(
            model=config.VLLM_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=_vllm_max_tokens(),
        )
        return (resp.choices[0].message.content or "").strip()

    client = _claude_client()
    resp = await client.messages.create(
        model=config.WORKER_MODEL,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=config.WORKER_MAX_TOKENS,
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ── 도구 사용 루프 (ReAct 대체) ───────────────────────────────────────────────


async def _run_claude(route: str, system: str, user_content: str, task_id: str) -> str:
    """Anthropic Agent SDK 도구 실행 루프 — tool_runner 가 도구 호출/결과 누적을 관리한다.

    도구 실행은 sdk_tools 의 @beta_async_tool 이 app.tools.execute 로 위임한다. 본 함수는
    각 모델 턴을 순회하며 도구 호출 알림(_notify)을 봇으로 스트리밍하고 최종 텍스트를 반환한다.
    """
    client = _claude_client()
    runner = client.beta.messages.tool_runner(
        model=config.WORKER_MODEL,
        system=system,
        max_tokens=config.WORKER_MAX_TOKENS,
        max_iterations=config.WORKER_MAX_ITERATIONS,
        tools=sdk_tools.sdk_tools_for(route),
        messages=[{"role": "user", "content": user_content}],
    )
    step = 0
    last_text = ""  # 최대 반복 도달 시 직전 텍스트를 폐기하지 않음
    async for message in runner:
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        if text:
            last_text = text
        for b in message.content:
            if b.type == "tool_use":
                step += 1
                await _notify(f"🔧 *{b.name}* (id=`{task_id}`, step {step})\n{str(b.input)[:120]}")
    return last_text or "(최대 반복 도달 — 부분 결과 없음)"


async def _run_vllm(system: str, user_content: str, task_id: str, schema: list[dict]) -> str:
    client = _vllm_client()
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    step = 0
    last_text = ""  # 도구 호출과 함께 나온 직전 텍스트 — 최대 반복 도달 시 폐기하지 않음
    for _ in range(config.WORKER_MAX_ITERATIONS):
        resp = await client.chat.completions.create(
            model=config.VLLM_MODEL,
            messages=messages,
            tools=schema,
            max_tokens=_vllm_max_tokens(),
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        text = (msg.content or "").strip()
        if not msg.tool_calls:
            return text
        if text:
            last_text = text
        for tc in msg.tool_calls:
            step += 1
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            await _notify(
                f"🔧 *{tc.function.name}* (id=`{task_id}`, step {step})\n{str(args)[:120]}"
            )
            out = await execute(tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
    return last_text or "(최대 반복 도달 — 부분 결과 없음)"


async def run_agent(route: str, system: str, user_content: str, task_id: str) -> str:
    """지정 라우트의 도구 셋으로 tool-use 루프 실행. 백엔드 자동 선택.

    Claude → Agent SDK tool_runner, vLLM → openai 호환 도구 루프.
    """
    if await select_backend(route) == "vllm":
        _, openai_schema = tools_for(route)
        return await _run_vllm(system, user_content, task_id, openai_schema)
    return await _run_claude(route, system, user_content, task_id)
