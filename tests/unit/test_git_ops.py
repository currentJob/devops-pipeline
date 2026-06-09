"""git_ops — 변경 수집/메시지 정제/커밋 적용 단위 테스트.

실제 git 프로세스는 _git 을 monkeypatch 해 대체한다 (서브프로세스/실 repo 불필요).
"""

from __future__ import annotations

import pytest

from app import config
from app.worker import git_ops


def _fake_git(responses: dict[tuple[str, ...], tuple[int, str]]):
    """(args) → (rc, out) 매핑으로 git_ops._git 을 대체하는 async 함수."""
    calls: list[tuple[str, ...]] = []

    async def fake(*args: str) -> tuple[int, str]:
        calls.append(args)
        return responses.get(args, (0, ""))

    fake.calls = calls
    return fake


async def test_collect_changes_empty(monkeypatch):
    monkeypatch.setattr(git_ops, "_git", _fake_git({("status", "--short"): (0, "")}))
    assert await git_ops.collect_changes() == ("", "")


async def test_collect_changes_returns_status_and_diff(monkeypatch):
    monkeypatch.setattr(
        git_ops,
        "_git",
        _fake_git(
            {
                ("status", "--short"): (0, " M app/foo.py"),
                ("diff", "HEAD"): (0, "diff --git a/app/foo.py ..."),
            }
        ),
    )
    status, diff = await git_ops.collect_changes()
    assert status == " M app/foo.py"
    assert diff.startswith("diff --git")


async def test_collect_changes_raises_on_git_error(monkeypatch):
    monkeypatch.setattr(
        git_ops, "_git", _fake_git({("status", "--short"): (128, "fatal: not a git repo")})
    )
    with pytest.raises(RuntimeError):
        await git_ops.collect_changes()


def test_strip_fences_removes_code_block():
    raw = "```\nFix: 버그 수정\n\n- 원인 설명\n```"
    assert git_ops._strip_fences(raw) == "Fix: 버그 수정\n\n- 원인 설명"


def test_strip_fences_plain_passthrough():
    raw = "Feat: 새 기능 추가"
    assert git_ops._strip_fences(raw) == "Feat: 새 기능 추가"


async def test_apply_commit_returns_oneline(monkeypatch):
    fake = _fake_git(
        {
            ("add", "-A"): (0, ""),
            ("commit", "-m", "Fix: 수정"): (0, "[main abc] Fix: 수정"),
            ("log", "-1", "--oneline"): (0, "abc1234 Fix: 수정"),
        }
    )
    monkeypatch.setattr(git_ops, "_git", fake)
    assert await git_ops.apply_commit("Fix: 수정") == "abc1234 Fix: 수정"


async def test_apply_commit_raises_when_commit_fails(monkeypatch):
    fake = _fake_git(
        {
            ("add", "-A"): (0, ""),
            ("commit", "-m", "Fix: 수정"): (1, "nothing to commit"),
        }
    )
    monkeypatch.setattr(git_ops, "_git", fake)
    with pytest.raises(RuntimeError, match="git commit 실패"):
        await git_ops.apply_commit("Fix: 수정")


# ── push ──────────────────────────────────────────────────────────────────────


def test_authenticated_url_injects_token():
    url = git_ops._authenticated_url("https://github.com/o/r.git", "ghp_secret")
    assert url == "https://x-access-token:ghp_secret@github.com/o/r.git"


def test_authenticated_url_rejects_non_https():
    with pytest.raises(RuntimeError, match="HTTPS"):
        git_ops._authenticated_url("git@github.com:o/r.git", "ghp_secret")


def test_redact_hides_token(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", "ghp_secret")
    assert git_ops._redact("error at ghp_secret@github.com") == "error at ***@github.com"


def test_redact_noop_when_no_token(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")
    assert git_ops._redact("nothing to hide") == "nothing to hide"


async def test_pending_commits_no_upstream(monkeypatch):
    monkeypatch.setattr(
        git_ops,
        "_git",
        _fake_git({("rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"): (1, "")}),
    )
    assert await git_ops.pending_commits("main") is None


async def test_pending_commits_lists_ahead(monkeypatch):
    monkeypatch.setattr(
        git_ops,
        "_git",
        _fake_git(
            {
                ("rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"): (0, "abc"),
                ("log", "origin/main..HEAD", "--oneline"): (0, "abc1234 Feat: x"),
            }
        ),
    )
    assert await git_ops.pending_commits("main") == "abc1234 Feat: x"


async def test_push_requires_token(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN 미설정"):
        await git_ops.push("main")


async def test_push_redacts_token_on_failure(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", "ghp_secret")
    fake = _fake_git(
        {
            ("remote", "get-url", "origin"): (0, "https://github.com/o/r.git"),
            (
                "push",
                "https://x-access-token:ghp_secret@github.com/o/r.git",
                "HEAD:main",
            ): (1, "fatal: auth failed for https://x-access-token:ghp_secret@github.com"),
        }
    )
    monkeypatch.setattr(git_ops, "_git", fake)
    with pytest.raises(RuntimeError) as exc:
        await git_ops.push("main")
    assert "ghp_secret" not in str(exc.value)
    assert "***" in str(exc.value)
