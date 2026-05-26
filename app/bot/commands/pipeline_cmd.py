import asyncio
import logging

from telegram import Update
from telegram.ext import Application, ContextTypes

from app.bot import notifier
from app.bot.commands import _authorized, _state
from app.pipeline import runner as pipeline

logger = logging.getLogger(__name__)


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    if _state.running:
        await update.message.reply_text("⚠️ 파이프라인이 이미 실행 중입니다.")
        return

    await update.message.reply_text("▶️ 파이프라인을 시작합니다...")
    asyncio.create_task(_run_pipeline(context.application))


async def _run_pipeline(app: Application) -> None:
    _state.running = True
    try:
        await pipeline.run(app)
    except Exception:
        logger.exception("파이프라인 오류")
        await notifier.send_message(app, "🔴 *오류*: 파이프라인이 예기치 않게 종료되었습니다.")
    finally:
        _state.running = False
