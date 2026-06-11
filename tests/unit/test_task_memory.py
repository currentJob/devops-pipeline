"""작업 메모리 + DB 백엔드 — 요약 저장/조회, 컨텍스트 주입, URL 전환 단위 테스트.

SQLite(aiosqlite) 임시 DB 로 검증한다. PostgreSQL 은 URL 구성만 검증(연결 불필요).
"""

from __future__ import annotations

import pytest

from app import config
from app.agent import graph
from app.worker import store


@pytest.fixture
async def temp_store(tmp_path, monkeypatch):
    """임시 SQLite DB 로 엔진을 교체하고 초기화."""
    monkeypatch.setattr(config, "DB_BACKEND", "sqlite")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    await store.dispose()  # 기존(전역) 엔진 정리 후 임시 경로로 재생성
    await store.init()
    yield store
    await store.dispose()


# ── DB URL 전환 ───────────────────────────────────────────────────────────────


def test_database_url_postgres(monkeypatch):
    monkeypatch.setattr(config, "DB_BACKEND", "postgres")
    monkeypatch.setattr(config, "POSTGRES_USER", "u")
    monkeypatch.setattr(config, "POSTGRES_PASSWORD", "p")
    monkeypatch.setattr(config, "POSTGRES_HOST", "h")
    monkeypatch.setattr(config, "POSTGRES_PORT", 5432)
    monkeypatch.setattr(config, "POSTGRES_DB", "d")
    assert store._database_url() == "postgresql+asyncpg://u:p@h:5432/d"


def test_database_url_sqlite(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_BACKEND", "sqlite")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert store._database_url().startswith("sqlite+aiosqlite:///")


# ── 요약 저장/조회 ────────────────────────────────────────────────────────────


async def test_summary_roundtrip(temp_store):
    await temp_store.create("t1", "첫 작업")
    await temp_store.set_summary("t1", "auth.py SQL 인젝션 2건 지적")
    rows = await temp_store.get_recent_summaries(3)
    assert len(rows) == 1
    assert rows[0]["summary"] == "auth.py SQL 인젝션 2건 지적"


async def test_get_recent_summaries_excludes_empty(temp_store):
    await temp_store.create("t1", "요약 있음")
    await temp_store.set_summary("t1", "요약 A")
    await temp_store.create("t2", "요약 없음")  # set_summary 미호출 → 제외
    rows = await temp_store.get_recent_summaries(5)
    assert [r["summary"] for r in rows] == ["요약 A"]


async def test_get_recent_summaries_limit_zero(temp_store):
    await temp_store.create("t1", "x")
    await temp_store.set_summary("t1", "요약")
    assert await temp_store.get_recent_summaries(0) == []


async def test_create_is_idempotent(temp_store):
    await temp_store.create("t1", "처음")
    await temp_store.create("t1", "중복 — 무시되어야 함")
    rows = await temp_store.get_recent(10)
    assert len(rows) == 1
    assert rows[0]["description"] == "처음"


# ── 메모리 블록 주입 ──────────────────────────────────────────────────────────


async def test_memory_block_disabled_when_count_zero(temp_store, monkeypatch):
    monkeypatch.setattr(config, "WORKER_MEMORY_COUNT", 0)
    await temp_store.create("t1", "x")
    await temp_store.set_summary("t1", "무시될 요약")
    assert await graph._recent_memory_block() == ""


async def test_memory_block_formats_summaries(temp_store, monkeypatch):
    monkeypatch.setattr(config, "WORKER_MEMORY_COUNT", 3)
    await temp_store.create("t1", "x")
    await temp_store.set_summary("t1", "React 트렌드 vault 노트 생성")
    block = await graph._recent_memory_block()
    assert "[이전 작업 메모리]" in block
    assert "React 트렌드 vault 노트 생성" in block


async def test_memory_block_empty_when_no_summaries(temp_store, monkeypatch):
    monkeypatch.setattr(config, "WORKER_MEMORY_COUNT", 3)
    assert await graph._recent_memory_block() == ""
