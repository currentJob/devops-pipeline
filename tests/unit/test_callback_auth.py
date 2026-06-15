"""콜백 핸들러 인가 — 미인가 chat 의 콜백 거부 단위 테스트 (defense-in-depth)."""

from __future__ import annotations

from app.bot import notifier
from app.bot.commands import git_cmd

# conftest 가 TELEGRAM_CHAT_ID=0 을 주입 — 999 는 미인가 chat
_UNAUTHORIZED = 999


class _FakeQuery:
    def __init__(self, data: str):
        self.data = data
        self.answered: str | None = None
        self.edited: str | None = None
        self.message = type("M", (), {"text": "preview"})()

    async def answer(self, text: str | None = None):
        self.answered = text

    async def edit_message_reply_markup(self, reply_markup=None):
        pass

    async def edit_message_text(self, text: str):
        self.edited = text


class _FakeUpdate:
    def __init__(self, chat_id: int, data: str):
        self.effective_chat = type("C", (), {"id": chat_id})()
        self.callback_query = _FakeQuery(data)


async def test_commit_callback_rejects_unauthorized():
    upd = _FakeUpdate(_UNAUTHORIZED, "commit_apply:tok")
    await git_cmd.handle_commit_callback(upd, None)
    assert upd.callback_query.answered == "권한 없음"
    assert upd.callback_query.edited is None  # 처리로 진입하지 않음


async def test_push_callback_rejects_unauthorized():
    upd = _FakeUpdate(_UNAUTHORIZED, "push_apply:tok")
    await git_cmd.handle_push_callback(upd, None)
    assert upd.callback_query.answered == "권한 없음"
    assert upd.callback_query.edited is None


async def test_approval_callback_rejects_unauthorized():
    upd = _FakeUpdate(_UNAUTHORIZED, "approve:tid")
    await notifier._handle_callback(upd, None)
    assert upd.callback_query.answered == "권한 없음"
