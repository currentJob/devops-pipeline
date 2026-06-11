import logging
import time
import uuid
from dataclasses import dataclass

import aiohttp
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from app import config

logger = logging.getLogger(__name__)


@dataclass
class BotState:
    running: bool = False
    start_time: float | None = None


_state = BotState()


def _authorized(update: Update) -> bool:
    """등록된 chat_id 에서만 명령 허용."""
    return update.effective_chat.id == config.TELEGRAM_CHAT_ID


def _format_uptime(seconds: float) -> str:
    """초 → '2시간 30분 5초' 같은 사람용 문자열."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    parts: list[str] = []
    if h:
        parts.append(f"{h}시간")
    if m:
        parts.append(f"{m}분")
    parts.append(f"{s}초")
    return " ".join(parts)


async def _dispatch_to_worker(
    update: Update, description: str, save_to_vault: bool = False
) -> None:
    """공통 패턴: 워커에 작업 위임 + 즉시 '작업 시작' 응답."""
    task_id = str(uuid.uuid4())[:8]
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                config.WORKER_URL,
                json={
                    "task_id": task_id,
                    "description": description,
                    "save_to_vault": save_to_vault,
                },
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp,
        ):
            if resp.status != 202:
                body = await resp.text()
                await update.message.reply_text(
                    f"⚠️ 워커 응답: {resp.status}\n{body}",
                )
                return
    except aiohttp.ClientError as e:
        logger.warning("워커 통신 실패 task_id=%s: %s", task_id, e)
        await update.message.reply_text(f"🔴 워커 통신 실패: {e}")
        return

    await update.message.reply_text(
        f"🚀 *작업 시작* (id=`{task_id}`)\n\n처리 후 알림 드립니다.",
        parse_mode="Markdown",
    )


def register_commands(app: Application) -> None:
    _state.start_time = time.monotonic()

    # 지연 import: 순환 참조 방지 (submodule 들이 이 __init__ 을 import 하므로)
    from app.bot.commands.git_cmd import (
        cmd_commit,
        cmd_push,
        handle_commit_callback,
        handle_push_callback,
    )
    from app.bot.commands.pipeline_cmd import cmd_run
    from app.bot.commands.system import (
        cmd_health,
        cmd_help,
        cmd_model,
        cmd_start,
        cmd_status,
        cmd_uptime,
    )
    from app.bot.commands.worker_cmd import (
        cmd_audit,
        cmd_code,
        cmd_diff,
        cmd_doc,
        cmd_history,
        cmd_infra,
        cmd_lint,
        cmd_plan,
        cmd_stack,
        cmd_task,
        cmd_test,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("task", cmd_task))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("code", cmd_code))
    app.add_handler(CommandHandler("doc", cmd_doc))
    app.add_handler(CommandHandler("infra", cmd_infra))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("uptime", cmd_uptime))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("lint", cmd_lint))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("audit", cmd_audit))
    app.add_handler(CommandHandler("diff", cmd_diff))
    app.add_handler(CommandHandler("stack", cmd_stack))
    app.add_handler(CommandHandler("commit", cmd_commit))
    app.add_handler(
        CallbackQueryHandler(handle_commit_callback, pattern=r"^commit_(apply|cancel):")
    )
    app.add_handler(CommandHandler("push", cmd_push))
    app.add_handler(CallbackQueryHandler(handle_push_callback, pattern=r"^push_(apply|cancel):"))
