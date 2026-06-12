"""정기 다이제스트(app.worker.digest) 단위 테스트.

runtime.chat / recent_research 를 모킹하여 네트워크·LLM 없이 검증.
"""

from __future__ import annotations

import datetime

import pytest

from app import config
from app.tools import filesystem
from app.worker import digest


@pytest.fixture(autouse=True)
def _temp_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(filesystem, "WORKSPACE", tmp_path)
    monkeypatch.setattr(config, "VAULT_INDEX_ENABLED", False)  # vault_save 인덱싱 no-op
    return tmp_path / "vault"


def _make_note(vault, name, created, tags):
    vault.mkdir(parents=True, exist_ok=True)
    block = "\n".join(f"  - {t}" for t in tags)
    text = f'---\ntitle: "{name}"\ncreated: {created}\ntags:\n{block}\n---\n\n본문 {name}'
    (vault / f"{name}.md").write_text(text, encoding="utf-8")


def test_recent_notes_filters_by_date_and_kind(_temp_vault):
    today = datetime.date.today().isoformat()
    old = (datetime.date.today() - datetime.timedelta(days=40)).isoformat()
    _make_note(_temp_vault, "최신", today, ["type/research", "tech/qdrant"])
    _make_note(_temp_vault, "오래됨", old, ["type/doc"])
    _make_note(_temp_vault, "지난브리핑", today, ["type/digest"])
    (_temp_vault / "_MOC_x.md").write_text("생성물", encoding="utf-8")

    notes = digest._recent_notes(_temp_vault, days=7)
    titles = [t for t, _, _ in notes]
    assert titles == ["최신"]  # 오래됨/지난브리핑/_생성물 제외


def test_dominant_tech():
    notes = [
        ("a", "x", ["tech/qdrant", "area/db"]),
        ("b", "y", ["tech/qdrant"]),
        ("c", "z", ["tech/rust"]),
    ]
    assert digest._dominant_tech(notes) == "qdrant"
    assert digest._dominant_tech([("a", "x", ["area/db"])]) == ""


async def test_generate_digest_no_notes(_temp_vault, monkeypatch):
    result = await digest.generate_digest(days=7)
    assert "저장 완료" in result
    note = next(_temp_vault.rglob("주간 브리핑*.md"))
    text = note.read_text(encoding="utf-8")
    assert "type/digest" in text
    assert "새로 추가된 노트가 없습니다" in text


async def test_generate_digest_summarizes(_temp_vault, monkeypatch):
    today = datetime.date.today().isoformat()
    _make_note(_temp_vault, "Qdrant 노트", today, ["type/research", "tech/qdrant"])

    async def _fake_chat(system, user, route=None):
        assert "Qdrant 노트" in user  # 신규 노트가 프롬프트에 포함
        return "> [!summary] TL;DR\n> 요약본.\n\n## 주요 내용\n- Qdrant"

    async def _fake_research(topic):
        return "조사 비활성"  # 에러 prefix → 무시되어야 함

    monkeypatch.setattr(digest.runtime, "chat", _fake_chat)
    monkeypatch.setattr(digest, "recent_research", _fake_research)

    result = await digest.generate_digest(days=7)
    assert "저장 완료" in result
    text = next(_temp_vault.rglob("주간 브리핑*.md")).read_text(encoding="utf-8")
    assert "주요 내용" in text
    assert "type/digest" in text
