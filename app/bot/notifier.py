import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from app import config

logger = logging.getLogger(__name__)

_pending: dict[str, dict] = {}


def register_handlers(app: Application) -> None:
    # 승인/거절 콜백만 처리 — commit_ 등 다른 콜백을 가로채지 않도록 패턴 한정
    app.add_handler(CallbackQueryHandler(_handle_callback, pattern=r"^(approve|reject):"))


async def request_approval(app: Application, task_id: str, message: str) -> bool:
    event = asyncio.Event()
    result: dict = {"approved": None}
    _pending[task_id] = {"event": event, "result": result}

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ 승인", callback_data=f"approve:{task_id}"),
                InlineKeyboardButton("❌ 거절", callback_data=f"reject:{task_id}"),
            ]
        ]
    )

    await app.bot.send_message(
        chat_id=config.TELEGRAM_CHAT_ID,
        text=f"🔔 *검토 요청*\n\n{message}\n\n⏰ {config.APPROVAL_TIMEOUT // 60}분 내 응답 없으면 자동 중단",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    logger.info("승인 요청 발송 task_id=%s", task_id)

    try:
        await asyncio.wait_for(event.wait(), timeout=config.APPROVAL_TIMEOUT)
        approved = result["approved"]
        logger.info("응답 수신 task_id=%s approved=%s", task_id, approved)
        return approved
    except TimeoutError:
        logger.warning("승인 타임아웃 task_id=%s", task_id)
        await app.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID, text="⏰ 타임아웃 - 작업이 자동 중단되었습니다."
        )
        return False
    finally:
        _pending.pop(task_id, None)


async def send_message(app: Application, text: str) -> None:
    # Markdown 파싱 실패(불균형 특수문자) 시 평문으로 폴백 — 알림 유실 방지.
    try:
        await app.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
        )
    except TelegramError as e:
        logger.warning("Markdown 전송 실패 → 평문 재시도: %s", e)
        await app.bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=text)


async def _handle_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    action, task_id = query.data.split(":", 1)

    if task_id not in _pending:
        await query.answer("이미 처리된 요청입니다.")
        return

    approved = action == "approve"
    _pending[task_id]["result"]["approved"] = approved
    _pending[task_id]["event"].set()

    status = "✅ 승인됨" if approved else "❌ 거절됨"
    await query.edit_message_text(f"{query.message.text}\n\n→ {status}")
    await query.answer()
