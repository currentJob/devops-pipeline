"""`/pocrun <slug>` — /poc 가 만든 PoC 를 격리 샌드박스에서 build + 단일 실행(디버깅).

⚠️ LLM 생성 코드 실행 = 임의 코드 실행. pocsandbox 사이드카가 정적검사+무-egress 실행+
자원캡+자동 teardown 으로 제한한다. 실행 전 인라인 확인 + 인가 chat 재확인(휴먼게이트).
"""

from __future__ import annotations

import logging
import uuid

import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app import config
from app.bot.commands import _authorized
from app.pipeline import poc_eval

logger = logging.getLogger(__name__)

# token → slug (확인 콜백이 참조). 봇 프로세스 메모리에만.
_pending: dict[str, str] = {}

# build(≤300s)+run(≤60s)+teardown 여유
_RUN_TIMEOUT_S = 600
_EVAL_TIMEOUT_S = 180  # 평가(정적지표 + LLM 종합)
_BUILD_LOG_MAX = 1500  # 평가 요약과 함께 실으려 build 로그 축약


async def cmd_pocrun(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    slug = (context.args[0] if context.args else "").strip()
    if not slug:
        await update.message.reply_text(
            "사용법: `/pocrun <slug>`\n예: `/pocrun duckdb-mcp-pipeline`\n"
            "(/poc 가 만든 prompts/output/poc/<slug> 를 격리 실행)",
            parse_mode="Markdown",
        )
        return

    token = str(uuid.uuid4())[:8]
    _pending[token] = slug
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ 격리 실행", callback_data=f"pocrun_apply:{token}"),
                InlineKeyboardButton("❌ 취소", callback_data=f"pocrun_cancel:{token}"),
            ]
        ]
    )
    await update.message.reply_text(
        f"⚠️ PoC 격리 실행 — `{slug}`\n\n"
        "LLM 이 생성한 코드를 build + 단일 실행합니다(무-egress·자원캡·자동 정리).\n"
        "신뢰할 수 있는 PoC 인지 확인 후 진행하세요. 계속할까요?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def handle_pocrun_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not _authorized(update):  # 콜백도 인가된 chat 에서만
        await query.answer("권한 없음")
        return
    action, token = query.data.split(":", 1)
    slug = _pending.pop(token, None)
    if slug is None:
        await query.answer("만료되었거나 이미 처리된 요청입니다.")
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if action == "pocrun_cancel":
        await query.edit_message_text(f"{query.message.text}\n\n→ ❌ 취소됨")
        await query.answer()
        return

    await query.answer("격리 실행 중... (build 포함 수 분 소요)")
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                config.POCSANDBOX_RUN_URL,
                json={"slug": slug},
                timeout=aiohttp.ClientTimeout(total=_RUN_TIMEOUT_S),
            ) as resp,
            # pocsandbox 미기동(profile poc 안 띄움) 등은 ClientError 로 처리
        ):
            data = await resp.json()
    except aiohttp.ClientError as e:
        logger.warning("pocsandbox 통신 실패 slug=%s: %s", slug, e)
        await query.edit_message_text(
            f"{query.message.text}\n\n→ 🔴 샌드박스 연결 실패: {e}\n"
            "`docker compose --profile poc up -d pocsandbox` 로 사이드카를 띄웠는지 확인하세요."
        )
        return

    icon = "✅" if data.get("ok") else "🔴"
    stage = data.get("stage", "?")
    logs = (data.get("logs") or "")[:_BUILD_LOG_MAX]
    build_block = f"{icon} PoC 격리 실행 — `{slug}` (stage: {stage})\n\n```\n{logs}\n```"
    await query.edit_message_text(
        f"{build_block}\n\n🧪 평가 중... (정적지표 + LLM 종합)", parse_mode="Markdown"
    )

    # 통합 평가: build 결과를 worker 로 보내 EVALUATION.md 생성 + 요약 회신.
    # (bot 은 read-only 라 PoC 파일에 접근 불가 → 평가 본체는 worker 가 수행)
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                config.WORKER_POC_EVAL_URL,
                json={"slug": slug, "build_result": data},
                timeout=aiohttp.ClientTimeout(total=_EVAL_TIMEOUT_S),
            ) as resp,
        ):
            eval_data = await resp.json()
    except aiohttp.ClientError as e:
        logger.warning("PoC 평가 호출 실패 slug=%s: %s", slug, e)
        await query.edit_message_text(
            f"{build_block}\n\n🟡 평가 생략 — worker 연결 실패: {e}", parse_mode="Markdown"
        )
        return

    if not eval_data.get("ok"):
        await query.edit_message_text(
            f"{build_block}\n\n🟡 평가 실패: {eval_data.get('detail', '?')}",
            parse_mode="Markdown",
        )
        return

    await query.edit_message_text(
        f"{build_block}\n\n{poc_eval.format_telegram_summary(eval_data)}",
        parse_mode="Markdown",
    )
