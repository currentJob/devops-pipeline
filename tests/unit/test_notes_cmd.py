"""`/notes` 발행 토글 — 콜백 핸들러 + 키보드 헬퍼 통합 테스트.

aiohttp 네트워크 경로는 _post_publish/_apply_and_report 를 monkeypatch 로 대체해
핸들러 분기(인가·만료·토글·닫기·적용 확인)를 검증한다.
"""

from __future__ import annotations

import pytest

from app.bot.commands import notes_cmd

# conftest 가 TELEGRAM_CHAT_ID=0 주입 — 0=인가, 999=미인가
_AUTH = 0
_UNAUTH = 999


class _FakeQuery:
    def __init__(self, data: str):
        self.data = data
        self.answered: str | None = None
        self.edited_text: str | None = None
        self.markup_calls: list = []
        self.message = type("M", (), {"text": "기존 메시지"})()

    async def answer(self, text: str | None = None):
        self.answered = text

    async def edit_message_reply_markup(self, reply_markup=None):
        self.markup_calls.append(reply_markup)

    async def edit_message_text(self, text: str, reply_markup=None):
        self.edited_text = text


class _FakeUpdate:
    def __init__(self, chat_id: int, data: str):
        self.effective_chat = type("C", (), {"id": chat_id})()
        self.callback_query = _FakeQuery(data)


@pytest.fixture(autouse=True)
def _clear_sessions():
    notes_cmd._sessions.clear()
    yield
    notes_cmd._sessions.clear()


def _row(path="IT 트렌드/a.md", title="A", category="IT 트렌드", published=False):
    return {"path": path, "title": title, "category": category, "published": published}


# ── 순수 헬퍼 ─────────────────────────────────────────────────────────────────


def test_label_icon_and_category():
    assert notes_cmd._label(_row(published=True)).startswith("✅")
    assert notes_cmd._label(_row(published=False)).startswith("⬜")
    assert "IT 트렌드/A" in notes_cmd._label(_row())
    assert notes_cmd._label(_row(category="")) == "⬜ A"  # 루트는 카테고리 접두 없음


def test_build_keyboard_has_toggle_and_footer():
    kb = notes_cmd._build_keyboard("tok", [_row(), _row(path="b.md", title="B")])
    rows = kb.inline_keyboard
    assert len(rows) == 3  # 노트 2 + 푸터 1
    assert rows[0][0].callback_data == "vnt:tog:tok:0"
    assert [b.callback_data for b in rows[-1]] == ["vnt:apply:tok", "vnt:close:tok"]


# ── 콜백 핸들러 분기 ──────────────────────────────────────────────────────────


async def test_callback_rejects_unauthorized():
    upd = _FakeUpdate(_UNAUTH, "vnt:close:tok")
    await notes_cmd.handle_notes_callback(upd, None)
    assert upd.callback_query.answered == "권한 없음"


async def test_callback_expired_token():
    upd = _FakeUpdate(_AUTH, "vnt:tog:gone:0")
    await notes_cmd.handle_notes_callback(upd, None)
    assert "만료" in upd.callback_query.answered
    assert upd.callback_query.markup_calls == [None]  # 키보드 제거


async def test_toggle_flips_state(monkeypatch):
    notes_cmd._sessions["t1"] = [_row(published=False)]

    async def _ok(path, publish):
        return True

    monkeypatch.setattr(notes_cmd, "_post_publish", _ok)
    upd = _FakeUpdate(_AUTH, "vnt:tog:t1:0")
    await notes_cmd.handle_notes_callback(upd, None)

    assert notes_cmd._sessions["t1"][0]["published"] is True
    assert upd.callback_query.answered == "✅ 발행 표시"
    assert upd.callback_query.markup_calls  # 키보드 재렌더됨


async def test_toggle_failure_keeps_state(monkeypatch):
    notes_cmd._sessions["t1"] = [_row(published=False)]

    async def _fail(path, publish):
        return False

    monkeypatch.setattr(notes_cmd, "_post_publish", _fail)
    upd = _FakeUpdate(_AUTH, "vnt:tog:t1:0")
    await notes_cmd.handle_notes_callback(upd, None)

    assert notes_cmd._sessions["t1"][0]["published"] is False  # 변경 안 됨
    assert "실패" in upd.callback_query.answered


async def test_close_pops_session():
    notes_cmd._sessions["t1"] = [_row()]
    upd = _FakeUpdate(_AUTH, "vnt:close:t1")
    await notes_cmd.handle_notes_callback(upd, None)
    assert "t1" not in notes_cmd._sessions
    assert upd.callback_query.markup_calls == [None]


async def test_apply_shows_confirm():
    notes_cmd._sessions["t1"] = [_row(published=True), _row(path="b.md", published=False)]
    upd = _FakeUpdate(_AUTH, "vnt:apply:t1")
    await notes_cmd.handle_notes_callback(upd, None)

    assert "발행 적용" in upd.callback_query.edited_text
    assert "1개" in upd.callback_query.edited_text  # 공개 1개 집계
    assert "t1" in notes_cmd._sessions  # 확인 단계 — 아직 세션 유지


async def test_applyok_pops_and_reports(monkeypatch):
    notes_cmd._sessions["t1"] = [_row(published=True)]
    called = {"report": False}

    async def _report(query):
        called["report"] = True

    monkeypatch.setattr(notes_cmd, "_apply_and_report", _report)
    upd = _FakeUpdate(_AUTH, "vnt:applyok:t1")
    await notes_cmd.handle_notes_callback(upd, None)

    assert called["report"] is True
    assert "t1" not in notes_cmd._sessions  # 적용 시작 시 세션 정리
