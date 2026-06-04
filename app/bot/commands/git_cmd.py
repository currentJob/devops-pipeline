"""`/commit` — 변경 내역 기반 커밋 메시지를 생성해 미리보기 후, 확인 시 로컬 커밋.

흐름: /commit → 워커가 diff 로 메시지 생성(미리보기) → 인라인 버튼으로 확인
     → [✅ 커밋] 누르면 워커가 git add -A + commit (원격 push 는 하지 않음).
보안: 쓰기 git 은 워커의 git_ops 모듈에서만 실행되며, 에이전트 bash 도구와 분리돼 있다.
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

# token → 생성된 커밋 메시지 (인라인 버튼 콜백이 참조). 봇 프로세스 메모리에만 보관.
_pending: dict[str, str] = {}


async def cmd_commit(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    await update.message.reply_text("🔍 변경 내역 분석 중...")
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                config.WORKER_COMMIT_URL,
                json={"apply": False},
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp,
        ):
            if resp.status != 200:
                body = await resp.text()
                await update.message.reply_text(f"⚠️ 미리보기 실패 (HTTP {resp.status})\n{body}")
                return
            data = await resp.json()
    except aiohttp.ClientError as e:
        logger.warning("커밋 미리보기 통신 실패: %s", e)
        await update.message.reply_text(f"🔴 워커 통신 실패: {e}")
        return

    if not data.get("has_changes"):
        await update.message.reply_text("✅ 커밋할 변경 사항이 없습니다.")
        return

    message = data["message"]
    summary = data["summary"]
    token = str(uuid.uuid4())[:8]
    _pending[token] = message

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ 커밋", callback_data=f"commit_apply:{token}"),
                InlineKeyboardButton("❌ 취소", callback_data=f"commit_cancel:{token}"),
            ]
        ]
    )
    # 메시지/파일목록은 마크다운 특수문자가 섞일 수 있어 plain text 로 전송 (이스케이프 회피)
    await update.message.reply_text(
        f"📝 커밋 미리보기 (원격 push 안 함)\n\n"
        f"— 커밋 메시지 —\n{message}\n\n"
        f"— 변경 파일 —\n{summary}",
        reply_markup=keyboard,
    )


async def handle_commit_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    action, token = query.data.split(":", 1)

    message = _pending.pop(token, None)
    if message is None:
        await query.answer("만료되었거나 이미 처리된 요청입니다.")
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if action == "commit_cancel":
        await query.edit_message_text(f"{query.message.text}\n\n→ ❌ 취소됨")
        await query.answer()
        return

    await query.answer("커밋 중...")
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                config.WORKER_COMMIT_URL,
                json={"apply": True, "message": message},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp,
        ):
            body = await resp.text()
            if resp.status != 200:
                await query.edit_message_text(
                    f"{query.message.text}\n\n→ 🔴 커밋 실패 (HTTP {resp.status})\n{body}"
                )
                return
            data = await resp.json()
    except aiohttp.ClientError as e:
        logger.warning("커밋 적용 통신 실패: %s", e)
        await query.edit_message_text(f"{query.message.text}\n\n→ 🔴 워커 통신 실패: {e}")
        return

    if data.get("ok"):
        await query.edit_message_text(
            f"{query.message.text}\n\n→ ✅ 커밋 완료\n{data.get('detail', '')}"
        )
    else:
        await query.edit_message_text(
            f"{query.message.text}\n\n→ 🔴 커밋 실패\n{data.get('detail', '')}"
        )
