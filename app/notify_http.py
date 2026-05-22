"""봇 프로세스 내부의 작은 HTTP 알림 엔드포인트.

POST /notify          body: {"text": "마크다운 메시지"}
  → 200 ok / 400 invalid / 503 send failed
POST /worker-result   body: {"task_id": "abc-12", "result": "..."}
  → 200 ok / 400 invalid / 503 send failed

호스트의 127.0.0.1:8765 만 컨테이너에 매핑되도록 docker-compose 에서 제어한다.
"""

from __future__ import annotations

import logging

from aiohttp import web
from telegram.error import TelegramError
from telegram.ext import Application

from app import config

logger = logging.getLogger(__name__)

HOST = "0.0.0.0"  # 컨테이너 내부 — 외부 노출은 docker-compose 포트 매핑이 제어
PORT = 8765


def _make_handler(bot_app: Application):
    async def handle(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="invalid json")

        text = (body.get("text") or "").strip()
        if not text:
            return web.Response(status=400, text="empty text")

        try:
            await bot_app.bot.send_message(
                chat_id=config.TELEGRAM_CHAT_ID,
                text=text,
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.warning("알림 전송 실패: %s", e)
            return web.Response(status=503, text=f"send failed: {e}")

        return web.Response(status=200, text="ok")

    return handle


def _make_worker_result_handler(bot_app: Application):
    """워커가 보낸 작업 결과를 텔레그램으로 전달."""

    async def handle(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="invalid json")

        task_id = body.get("task_id", "?")
        result = (body.get("result") or "").strip()
        if not result:
            return web.Response(status=400, text="empty result")

        text = f"✅ *작업 완료* (id=`{task_id}`)\n\n{result}"
        try:
            await bot_app.bot.send_message(
                chat_id=config.TELEGRAM_CHAT_ID,
                text=text,
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.warning("worker-result 전달 실패: %s", e)
            return web.Response(status=503, text=f"send failed: {e}")

        return web.Response(status=200, text="ok")

    return handle


async def start_server(bot_app: Application) -> web.AppRunner:
    """HTTP 서버를 시작하고 cleanup 용 AppRunner 를 반환."""
    web_app = web.Application()
    web_app.router.add_post("/notify", _make_handler(bot_app))
    web_app.router.add_post("/worker-result", _make_worker_result_handler(bot_app))
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    logger.info(
        "알림 HTTP 서버 시작: http://%s:%d  (POST /notify, /worker-result)",
        HOST,
        PORT,
    )
    return runner
