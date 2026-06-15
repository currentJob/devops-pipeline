"""bot.server 알림 발신 — Markdown 파싱 실패 시 평문 폴백 단위 테스트."""

from __future__ import annotations

from telegram.error import TelegramError

from app.bot import server


class _FakeBot:
    def __init__(self, fail_markdown: bool):
        self.fail_markdown = fail_markdown
        self.calls: list[dict] = []

    async def send_message(self, chat_id, text, parse_mode=None):
        self.calls.append({"text": text, "parse_mode": parse_mode})
        if parse_mode == "Markdown" and self.fail_markdown:
            raise TelegramError("can't parse entities")


class _FakeApp:
    def __init__(self, bot: _FakeBot):
        self.bot = bot


async def test_send_falls_back_to_plain_on_markdown_error():
    bot = _FakeBot(fail_markdown=True)
    await server._send(_FakeApp(bot), "깨진 _마크다운")
    assert len(bot.calls) == 2
    assert bot.calls[0]["parse_mode"] == "Markdown"
    assert bot.calls[1]["parse_mode"] is None  # 평문 재시도


async def test_send_markdown_success_no_fallback():
    bot = _FakeBot(fail_markdown=False)
    await server._send(_FakeApp(bot), "정상 *굵게*")
    assert len(bot.calls) == 1
    assert bot.calls[0]["parse_mode"] == "Markdown"
