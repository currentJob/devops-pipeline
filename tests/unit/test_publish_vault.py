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
    assert (out / "트렌드" / "pub.md").exists()  # 공개 카테고리명으로 정규화
    assert not (out / "트렌드" / "priv.md").exists()  # 미발행 제외


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


def test_export_preserves_articles_owned_by_another_publisher(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "pub.md").write_text("---\npublish: true\n---\nA", encoding="utf-8")
    out = tmp_path / "content"
    (out / "트렌드").mkdir(parents=True)
    external = out / "트렌드" / "harness-external.md"
    external.write_text("external", encoding="utf-8")

    pv.export(vault, out)
    (vault / "pub.md").write_text("---\ntitle: private\n---\nA", encoding="utf-8")
    pv.export(vault, out)

    assert external.read_text(encoding="utf-8") == "external"
    assert not (out / "pub.md").exists()


def test_export_rejects_an_unsafe_manifest_path(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    out = tmp_path / "content"
    out.mkdir()
    (out / pv.MANIFEST).write_text('["../outside.md"]', encoding="utf-8")

    try:
        pv.export(vault, out)
    except ValueError as exc:
        assert "안전하지 않은 경로" in str(exc)
    else:
        raise AssertionError("unsafe manifest path must be rejected")
