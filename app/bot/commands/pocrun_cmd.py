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

# autopilot 최악 경로: (max_iter+1)회 빌드(샌드박스 ≤600s) + max_iter회 LLM 수정 + 평가.
# worker 가 실제 완료해도 bot 이 먼저 끊겨 오탐("연결 실패")하지 않도록 반복 캡에서 파생.
# 진행은 /notify 로 중계되므로 이 긴 대기는 최종 요약 수신용일 뿐.
_AUTOPILOT_TIMEOUT_S = (config.POC_AUTOPILOT_MAX_ITERATIONS + 1) * 900 + 300


async def cmd_pocs(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/pocs` — /poc 가 생성한 PoC 목록 조회 (worker /poc/list)."""
    if not _authorized(update):
        return
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                config.WORKER_POC_LIST_URL, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp,
        ):
            data = await resp.json()
    except aiohttp.ClientError as e:
        await update.message.reply_text(f"🔴 워커 연결 실패: {e}")
        return

    pocs = data.get("pocs") or []
    if not pocs:
        await update.message.reply_text(
            "생성된 PoC 가 없습니다. `/poc [테마]` 로 만들 수 있어요.", parse_mode="Markdown"
        )
        return

    lines = [f"📦 *PoC 목록* ({len(pocs)}개)\n"]
    for p in pocs:
        flags = " ".join(
            f
            for f in ("🧪평가" if p["has_eval"] else "", "📋핸드오프" if p["has_handoff"] else "")
            if f
        )
        lines.append(f"• `{p['slug']}` — 파일 {p['file_count']}개 {flags}".rstrip())
    lines.append("\n실행·평가: `/pocrun <slug>`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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
                InlineKeyboardButton("✅ 자동 실행", callback_data=f"pocrun_apply:{token}"),
                InlineKeyboardButton("❌ 취소", callback_data=f"pocrun_cancel:{token}"),
            ]
        ]
    )
    await update.message.reply_text(
        f"⚠️ PoC 자동 파이프라인 — `{slug}`\n\n"
        "LLM 이 생성한 코드를 격리 build/run → 실패 시 자동 수정 후 재빌드 반복 → 평가까지 진행합니다.\n"
        "이 확인 1회가 최대 N회 격리 실행을 인가합니다(무-egress·자원캡·자동 정리).\n"
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

    await query.answer("자동 파이프라인 실행 중... (빌드·수정·평가, 수 분 소요)")
    await query.edit_message_text(
        f"⚙️ PoC autopilot — `{slug}`\n빌드 → (실패 시) 자동 수정 → 재빌드 → 평가 진행 중...\n"
        "_진행 상황은 알림으로 중계됩니다._",
        parse_mode="Markdown",
    )

    # worker 가 LangGraph 로 빌드↔수정 루프 + 평가까지 수행하고 최종 요약을 회신한다.
    # (bot 은 read-only 라 PoC 파일 접근/실행 불가 → 파이프라인 본체는 worker)
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                config.WORKER_POC_AUTOPILOT_URL,
                json={"slug": slug},
                timeout=aiohttp.ClientTimeout(total=_AUTOPILOT_TIMEOUT_S),
            ) as resp,
        ):
            data = await resp.json()
    except aiohttp.ClientError as e:
        logger.warning("autopilot 통신 실패 slug=%s: %s", slug, e)
        await query.edit_message_text(
            f"🔴 autopilot 연결 실패 — `{slug}`: {e}\n"
            "worker 기동과 `docker compose --profile poc up -d pocsandbox` 를 확인하세요.",
            parse_mode="Markdown",
        )
        return

    if not data.get("ok"):
        await query.edit_message_text(
            f"🔴 autopilot 실패 — `{slug}`: {data.get('detail', '?')}", parse_mode="Markdown"
        )
        return

    build_ok = data.get("build_ok")
    head = (
        f"{'✅' if build_ok else '🟡'} *PoC autopilot* — `{slug}`\n"
        f"{'✅ 빌드 성공' if build_ok else '🔴 빌드 미통과'} "
        f"(stage: {data.get('build_stage', '?')}, 자동 수정 {data.get('iterations', 0)}회)\n\n"
    )
    eval_data = data.get("eval") or {}
    summary = poc_eval.format_telegram_summary(eval_data) if eval_data else "_(평가 없음)_"
    await query.edit_message_text(head + summary, parse_mode="Markdown")
