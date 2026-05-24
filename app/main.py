import asyncio
import logging

from telegram.ext import Application

from app import config
from app.bot import commands, notifier
from app.bot.server import start_server

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    notifier.register_handlers(app)
    commands.register_commands(app)

    async with app:
        await app.start()
        await app.updater.start_polling()
        notify_runner = await start_server(app)
        logger.info("봇 대기 중 - 텔레그램에서 /run 으로 파이프라인 실행")
        await notifier.send_message(app, "🟢 *봇 시작됨* - `/run` 으로 파이프라인을 실행하세요")

        stop = asyncio.Event()
        try:
            await stop.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await notify_runner.cleanup()
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
