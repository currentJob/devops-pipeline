"""publish_ops — 발행 토글/목록/적용 단위 테스트."""

from __future__ import annotations

import pytest

from app.worker import publish_ops


def _write(vault, rel, text):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ── _set_fm_publish ───────────────────────────────────────────────────────────


def test_set_fm_publish_replaces_existing():
    text = "---\ntitle: x\npublish: false\n---\n\n본문"
    out = publish_ops._set_fm_publish(text, True)
    assert "publish: true" in out
    assert "publish: false" not in out
    assert out.endswith("본문")


def test_set_fm_publish_inserts_when_absent():
    text = "---\ntitle: x\ntags: []\n---\n\n본문"
    out = publish_ops._set_fm_publish(text, True)
    assert "publish: true" in out
    assert "title: x" in out  # 기존 필드 보존
    assert publish_ops.publish_vault.is_published(out)


def test_set_fm_publish_false_excludes():
    text = "---\npublish: true\n---\n본문"
    out = publish_ops._set_fm_publish(text, False)
    assert not publish_ops.publish_vault.is_published(out)


def test_set_fm_publish_no_frontmatter():
    out = publish_ops._set_fm_publish("프론트매터 없음", True)
    assert out.startswith("---\npublish: true\n---")


# ── list_notes ────────────────────────────────────────────────────────────────


def test_list_notes_hides_generated_and_digests(tmp_path):
    vault = tmp_path / "vault"
    _write(vault, "IT 트렌드/pub.md", '---\ntitle: "Q"\npublish: true\n---\nA')
    _write(vault, "IT 트렌드/priv.md", "---\ntitle: x\n---\nB")
    _write(vault, "_MOC.md", "---\npublish: true\n---\nGEN")
    _write(vault, "digests/d.md", "---\npublish: true\n---\nD")

    rows = publish_ops.list_notes(vault)

    paths = {r["path"] for r in rows}
    assert paths == {"IT 트렌드/pub.md", "IT 트렌드/priv.md"}  # _·digests 숨김
    pub = next(r for r in rows if r["path"] == "IT 트렌드/pub.md")
    assert pub["published"] is True
    assert pub["title"] == "Q"
    assert pub["category"] == "IT 트렌드"


def test_list_notes_sorted_by_category_then_title(tmp_path):
    vault = tmp_path / "vault"
    _write(vault, "b.md", "---\ntitle: zzz\n---\n")
    _write(vault, "arch/a.md", "---\ntitle: aaa\n---\n")
    rows = publish_ops.list_notes(vault)
    # 루트 카테고리("")가 폴더("arch")보다 먼저 — (category, title) 정렬
    assert [r["path"] for r in rows] == ["b.md", "arch/a.md"]


# ── set_publish (경로 안전) ───────────────────────────────────────────────────


def test_set_publish_toggles_file(tmp_path):
    vault = tmp_path / "vault"
    _write(vault, "n.md", "---\ntitle: x\n---\n본문")
    row = publish_ops.set_publish("n.md", True, vault)
    assert row == {"path": "n.md", "published": True}
    assert publish_ops.publish_vault.is_published((vault / "n.md").read_text(encoding="utf-8"))


def test_set_publish_rejects_traversal(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with pytest.raises(ValueError):
        publish_ops.set_publish("../secret.md", True, vault)


def test_set_publish_rejects_excluded(tmp_path):
    vault = tmp_path / "vault"
    _write(vault, "_MOC.md", "---\n---\n")
    with pytest.raises(ValueError):
        publish_ops.set_publish("_MOC.md", True, vault)


def test_set_publish_rejects_missing(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with pytest.raises(ValueError):
        publish_ops.set_publish("ghost.md", True, vault)


# ── apply (git 호출 mock) ─────────────────────────────────────────────────────


async def test_apply_skips_git_when_no_changes(monkeypatch):
    monkeypatch.setattr(publish_ops, "_export_site", lambda: 2)

    async def _no_change(paths, message):
        return None  # 스테이징 변경 없음

    called = {"push": False}

    async def _push(branch):
        called["push"] = True
        return "pushed"

    monkeypatch.setattr(publish_ops.git_ops, "commit_paths", _no_change)
    monkeypatch.setattr(publish_ops.git_ops, "push", _push)

    result = await publish_ops.apply()

    assert result["ok"] and result["count"] == 2
    assert called["push"] is False  # 변경 없으면 push 생략


async def test_apply_commits_and_pushes(monkeypatch):
    monkeypatch.setattr(publish_ops, "_export_site", lambda: 1)

    async def _commit(paths, message):
        assert paths == ["site/content"]  # 경로 한정 스테이징
        return "abc123 Docs: 발행"

    async def _branch():
        return "main"

    async def _push(branch):
        assert branch == "main"
        return "main → origin push 완료"

    monkeypatch.setattr(publish_ops.git_ops, "commit_paths", _commit)
    monkeypatch.setattr(publish_ops.git_ops, "current_branch", _branch)
    monkeypatch.setattr(publish_ops.git_ops, "push", _push)

    result = await publish_ops.apply()

    assert result["ok"] and result["count"] == 1
    assert "push 완료" in result["detail"]
