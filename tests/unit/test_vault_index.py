"""vault_index (Qdrant + fastembed 래퍼) 단위 테스트.

실제 Qdrant/임베딩 없이 client 를 stub 으로 대체하여 graceful 폴백·포맷을 검증.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app import config
from app.rag import vault_index


@dataclass
class _Hit:
    metadata: dict
    document: str
    score: float


class _FakeClient:
    def __init__(self):
        self.added: list[dict] = []

    def add(self, collection_name, documents, metadata, ids, **kwargs):
        self.added.append({"docs": documents, "meta": metadata, "ids": ids})

    def query(self, collection_name, query_text, limit):
        return [
            _Hit({"path": "archive/a.md", "title": "A"}, "내용 일부 텍스트", 0.91),
            _Hit({"path": "archive/b.md", "title": "B"}, "다른 노트", 0.80),
        ]


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(vault_index, "_client", None)
    monkeypatch.setattr(vault_index, "_down_until", 0.0)
    monkeypatch.setattr(config, "VAULT_INDEX_ENABLED", True)


# ── 비활성/미가용 → 폴백 신호 ─────────────────────────────────────────────────


def test_disabled_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VAULT_INDEX_ENABLED", False)
    assert vault_index.semantic_search("q") is None
    assert vault_index.index_note("a.md", "A", "text") is False
    assert vault_index.index_all(tmp_path) is None


def test_get_client_failure_marks_down(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("qdrant_client.QdrantClient", _boom)
    assert vault_index._get_client() is None
    # 실패 원인이 last_error 로 노출되어야 함 (/reindex 진단 메시지용)
    assert "connection refused" in (vault_index.last_error() or "")
    # 다운 윈도우 설정 → 이후 호출도 즉시 None (재연결 시도 안 함)
    assert vault_index.semantic_search("q") is None


# ── stub client 동작 ──────────────────────────────────────────────────────────


def test_semantic_search_formats(monkeypatch):
    monkeypatch.setattr(vault_index, "_get_client", lambda: _FakeClient())
    out = vault_index.semantic_search("질의", limit=5)
    assert out is not None
    assert "archive/a.md" in out
    assert "score=0.91" in out


def test_semantic_search_query_error_returns_none(monkeypatch):
    class _BadClient:
        def query(self, **k):
            raise RuntimeError("boom")

    monkeypatch.setattr(vault_index, "_get_client", lambda: _BadClient())
    assert vault_index.semantic_search("q") is None


def test_index_note_success(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(vault_index, "_get_client", lambda: fake)
    assert vault_index.index_note("archive/a.md", "A", "본문") is True
    assert fake.added and fake.added[0]["meta"][0]["path"] == "archive/a.md"


def test_index_all_counts_md(tmp_path, monkeypatch):
    (tmp_path / "x.md").write_text("hello", encoding="utf-8")
    sub = tmp_path / "archive"
    sub.mkdir()
    (sub / "y.md").write_text("world", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("nope", encoding="utf-8")
    fake = _FakeClient()
    monkeypatch.setattr(vault_index, "_get_client", lambda: fake)
    assert vault_index.index_all(tmp_path) == 2


def test_index_all_unavailable_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(vault_index, "_get_client", lambda: None)
    assert vault_index.index_all(tmp_path) is None
