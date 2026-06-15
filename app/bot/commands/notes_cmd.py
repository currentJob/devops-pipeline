"""`/notes` — vault 노트를 카테고리별로 나열하고 발행(publish) 플래그를 토글한다.

흐름: /notes → 노트별 ✅/⬜ 인라인 버튼 → 탭하면 워커가 frontmatter publish 토글
     → [🚀 발행 적용] → 2차 확인 → 워커가 export + site/content 커밋 + push
     → blog.yml 이 Quartz 로 빌드·배포.
보안: 콜백도 인가된 chat 에서만(_authorized). 발행 적용은 push 까지 가므로 확인 1단계.
"""

from __future__ import annotations

import logging
import uuid

import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app import config
from app.bot.commands import _authorized

logger = logging.getLogger(__name__)

# token → 노트 목록(rows). 봇 프로세스 메모리에만 보관, /notes 호출마다 새 토큰.
_sessions: dict[str, list[dict]] = {}


def _label(row: dict) -> str:
    icon = "✅" if row["published"] else "⬜"
    name = row["title"][:35]
    cat = row["category"]
    return f"{icon} {cat}/{name}" if cat else f"{icon} {name}"


def _build_keyboard(token: str, rows: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(_label(r), callback_data=f"vnt:tog:{token}:{i}")]
        for i, r in enumerate(rows)
    ]
    buttons.append(
        [
            InlineKeyboardButton("🚀 발행 적용", callback_data=f"vnt:apply:{token}"),
            InlineKeyboardButton("❌ 닫기", callback_data=f"vnt:close:{token}"),
        ]
    )
    return InlineKeyboardMarkup(buttons)


async def _post_publish(path: str, publish: bool) -> bool:
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                config.WORKER_VAULT_PUBLISH_URL,
                json={"path": path, "publish": publish},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp,
        ):
            data = await resp.json()
            return bool(data.get("ok"))
    except aiohttp.ClientError as e:
        logger.warning("발행 토글 통신 실패 path=%s: %s", path, e)
        return False


async def cmd_notes(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    await update.message.reply_text("📒 vault 노트 불러오는 중...")
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                config.WORKER_VAULT_NOTES_URL,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp,
        ):
            if resp.status != 200:
                body = await resp.text()
                await update.message.reply_text(f"⚠️ 목록 실패 (HTTP {resp.status})\n{body}")
                return
            data = await resp.json()
    except aiohttp.ClientError as e:
        logger.warning("노트 목록 통신 실패: %s", e)
        await update.message.reply_text(f"🔴 워커 통신 실패: {e}")
        return

    rows = data.get("notes", [])
    if not rows:
        await update.message.reply_text("발행 가능한 노트가 없습니다. (digests·생성물 제외)")
        return

    token = str(uuid.uuid4())[:8]
    _sessions[token] = rows
    header = (
        f"📒 vault 노트 {len(rows)}개 — 버튼으로 발행(✅)/비공개(⬜) 토글\n"
        "🚀 발행 적용 = export + commit + push (사이트 반영)"
    )
    if data.get("truncated"):
        header += "\n⚠️ 50개 초과 — 일부만 표시(나머지는 로컬에서 발행)"
    await update.message.reply_text(header, reply_markup=_build_keyboard(token, rows))


async def _apply_and_report(query) -> None:
    await query.answer("발행 적용 중...")
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                config.WORKER_VAULT_PUBLISH_APPLY_URL,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp,
        ):
            data = await resp.json()
    except aiohttp.ClientError as e:
        logger.warning("발행 적용 통신 실패: %s", e)
        await query.edit_message_text(f"{query.message.text}\n\n→ 🔴 워커 통신 실패: {e}")
        return

    if data.get("ok"):
        await query.edit_message_text(
            f"🚀 발행 적용\n\n→ ✅ 완료 (공개 {data.get('count', '?')}개)\n{data.get('detail', '')}"
        )
    else:
        await query.edit_message_text(
            f"🚀 발행 적용\n\n→ 🔴 실패\n{data.get('detail', '')}"
        )


async def handle_notes_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not _authorized(update):  # 콜백도 인가된 chat 에서만 (defense-in-depth)
        await query.answer("권한 없음")
        return

    parts = query.data.split(":")  # vnt:<action>:<token>[:<idx>]
    action = parts[1]
    token = parts[2] if len(parts) > 2 else ""
    rows = _sessions.get(token)
    if rows is None:
        await query.answer("만료된 목록입니다. /notes 를 다시 실행하세요.")
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if action == "close":
        _sessions.pop(token, None)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.answer("닫음")
        return

    if action == "tog":
        idx = int(parts[3])
        row = rows[idx]
        new_val = not row["published"]
        if not await _post_publish(row["path"], new_val):
            await query.answer("토글 실패 (워커 확인)")
            return
        row["published"] = new_val
        await query.answer("✅ 발행 표시" if new_val else "⬜ 비공개")
        await query.edit_message_reply_markup(reply_markup=_build_keyboard(token, rows))
        return

    if action == "apply":
        n_pub = sum(1 for r in rows if r["published"])
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ 확인", callback_data=f"vnt:applyok:{token}"),
                    InlineKeyboardButton("❌ 취소", callback_data=f"vnt:close:{token}"),
                ]
            ]
        )
        await query.edit_message_text(
            f"🚀 발행 적용\n\n공개 {n_pub}개를 site/content 로 export 후 commit·push 합니다.\n"
            "계속할까요?",
            reply_markup=keyboard,
        )
        await query.answer()
        return

    if action == "applyok":
        _sessions.pop(token, None)
        await _apply_and_report(query)
        return
