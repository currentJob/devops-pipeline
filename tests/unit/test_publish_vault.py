"""publish_vault export 스크립트 — 발행 필터 단위 테스트."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "publish_vault.py"
_spec = importlib.util.spec_from_file_location("publish_vault", _SCRIPT)
pv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pv)


def test_is_published():
    assert pv.is_published("---\ntitle: x\npublish: true\n---\n\n본문")
    assert pv.is_published("---\npublish: True\n---\n본문")  # 대소문자 무관
    assert not pv.is_published("---\ntitle: x\n---\n본문")  # 플래그 없음
    assert not pv.is_published("프론트매터 없음")


def _note(text: str) -> str:
    return text


def test_export_publishes_only_flagged(tmp_path):
    vault = tmp_path / "vault"
    (vault / "IT 트렌드").mkdir(parents=True)
    (vault / "IT 트렌드" / "pub.md").write_text("---\npublish: true\n---\nA", encoding="utf-8")
    (vault / "IT 트렌드" / "priv.md").write_text("---\ntitle: x\n---\nB", encoding="utf-8")
    out = tmp_path / "content"

    n = pv.export(vault, out)

    assert n == 1
    assert (out / "IT 트렌드" / "pub.md").exists()  # 발행 + 폴더(카테고리) 보존
    assert not (out / "IT 트렌드" / "priv.md").exists()  # 미발행 제외


def test_export_excludes_generated_and_digests(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "_MOC.md").write_text("---\npublish: true\n---\nGEN", encoding="utf-8")
    (vault / "digests").mkdir()
    (vault / "digests" / "d.md").write_text("---\npublish: true\n---\nD", encoding="utf-8")
    out = tmp_path / "content"

    n = pv.export(vault, out)

    assert n == 0  # publish 플래그가 있어도 _ 생성물·digests 는 제외
    assert not (out / "_MOC.md").exists()
    assert not (out / "digests" / "d.md").exists()


def test_export_generates_default_homepage(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("---\npublish: true\n---\nA", encoding="utf-8")
    out = tmp_path / "content"

    pv.export(vault, out)

    # index.md 가 발행 노트에 없으면 기본 홈페이지 생성
    assert (out / "index.md").exists()
    assert "publish: true" in (out / "index.md").read_text(encoding="utf-8")
