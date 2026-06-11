"""기동 자가점검(selfcheck) 단위 테스트 — 외부 의존성 없이 분기·crash-safety 검증."""

from __future__ import annotations

import pytest

from app import config
from app.tools import filesystem
from app.worker import selfcheck

# ── 임베딩 캐시 점검 (NO_SUCHFILE 손상 감지가 핵심) ──────────────────────────────


@pytest.fixture(autouse=True)
def _enable_index(monkeypatch):
    monkeypatch.setattr(config, "VAULT_INDEX_ENABLED", True)
    monkeypatch.setattr(config, "EMBED_MODEL", "vendor/some-model")


def test_embedding_no_cache_env(monkeypatch):
    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)
    r = selfcheck._check_embedding_cache()
    assert r["ok"] and "기본 위치" in r["detail"]


def test_embedding_cache_missing_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "nope"))
    r = selfcheck._check_embedding_cache()
    assert r["ok"] and "미다운로드" in r["detail"]


def test_embedding_cache_complete(monkeypatch, tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"x")
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path))
    r = selfcheck._check_embedding_cache()
    assert r["ok"] and "캐시됨" in r["detail"]


def test_embedding_cache_corrupt(monkeypatch, tmp_path):
    # 디렉터리·하위구조는 있으나 .onnx 가 없음 = 손상 (NO_SUCHFILE 원인)
    (tmp_path / "models--x" / "snapshots" / "abc").mkdir(parents=True)
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path))
    r = selfcheck._check_embedding_cache()
    assert not r["ok"] and "불완전" in r["detail"]


def test_embedding_disabled(monkeypatch):
    monkeypatch.setattr(config, "VAULT_INDEX_ENABLED", False)
    assert selfcheck._check_embedding_cache()["ok"]


# ── LLM 백엔드 점검 ───────────────────────────────────────────────────────────


def test_llm_claude(monkeypatch):
    monkeypatch.setattr(config, "CLAUDE_API_KEY", "sk-x")
    assert selfcheck._check_llm()["ok"]


def test_llm_none(monkeypatch):
    monkeypatch.setattr(config, "CLAUDE_API_KEY", "")
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "")
    r = selfcheck._check_llm()
    assert not r["ok"] and "미설정" in r["detail"]


# ── vault 점검 ────────────────────────────────────────────────────────────────


def test_vault_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(filesystem, "WORKSPACE", tmp_path)
    monkeypatch.setattr(config, "VAULT_SUBDIR", "vault")
    assert selfcheck._check_vault()["ok"]


def test_vault_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(filesystem, "WORKSPACE", tmp_path)
    monkeypatch.setattr(config, "VAULT_SUBDIR", "vault")
    (tmp_path / "vault").mkdir()
    (tmp_path / "vault" / "a.md").write_text("x", encoding="utf-8")
    r = selfcheck._check_vault()
    assert r["ok"] and "1개" in r["detail"]


# ── 오케스트레이션 crash-safety ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_checks_never_raises(monkeypatch):
    # 인덱스 비활성 → qdrant/embedding HTTP·다운로드 없이 빠르게 모든 항목 dict 반환
    monkeypatch.setattr(config, "VAULT_INDEX_ENABLED", False)
    checks = await selfcheck.run_checks()
    names = {c["name"] for c in checks}
    assert names == {"db", "workspace_git", "vault", "qdrant", "embedding", "llm"}
    for c in checks:
        assert set(c) == {"name", "ok", "detail"}
        assert isinstance(c["ok"], bool)
