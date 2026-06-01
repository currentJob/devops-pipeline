"""app/tools 도메인의 안전 가드 단위 테스트.

WORKSPACE 는 임시 디렉토리로 monkeypatch 하여 호스트 파일 시스템과 격리.
"""

from __future__ import annotations

import sys

import pytest

from app import tools
from app.tools import filesystem

# 워커는 Linux 컨테이너에서만 운영되므로, Windows 호스트의 unit 테스트 환경에서는
# 일부 POSIX 도구(ls 등) 가 없어 실제 subprocess 호출이 불가하다.
SKIP_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX 명령이 Windows host 에 없음 (실제 운영은 Linux 컨테이너)",
)


@pytest.fixture(autouse=True)
def _temp_workspace(tmp_path, monkeypatch):
    """WORKSPACE 를 격리된 임시 디렉토리로 교체."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "output").mkdir()
    (tmp_path / "secret.txt").write_text("super secret\n", encoding="utf-8")
    monkeypatch.setattr(filesystem, "WORKSPACE", tmp_path)
    return tmp_path


# ── read_file ────────────────────────────────────────────────────────────────


def test_read_file_valid_path():
    result = tools.read_file("app/main.py")
    assert "hello" in result


def test_read_file_missing():
    result = tools.read_file("does/not/exist.py")
    assert "파일 없음" in result


def test_read_file_absolute_rejected():
    result = tools.read_file("/etc/passwd")
    assert "거부" in result
    assert "absolute" in result


def test_read_file_traversal_rejected():
    result = tools.read_file("../../../etc/passwd")
    assert "거부" in result
    assert "traversal" in result


def test_read_file_size_limit(tmp_path):
    huge = tmp_path / "huge.bin"
    huge.write_bytes(b"x" * (filesystem.MAX_FILE_BYTES + 1))
    result = tools.read_file("huge.bin")
    assert "너무 큼" in result


# ── write_file ───────────────────────────────────────────────────────────────


def test_write_file_in_output_succeeds(_temp_workspace):
    result = tools.write_file("prompts/output/report.md", "# 보고서\n")
    assert "저장 완료" in result
    saved = (_temp_workspace / "prompts" / "output" / "report.md").read_text(encoding="utf-8")
    assert saved == "# 보고서\n"


def test_write_file_creates_parent_dirs(_temp_workspace):
    result = tools.write_file("prompts/output/sub/nested.md", "내용")
    assert "저장 완료" in result
    assert (_temp_workspace / "prompts" / "output" / "sub" / "nested.md").exists()


def test_write_file_outside_output_rejected():
    result = tools.write_file("app/main.py", "import os")
    assert "쓰기 거부" in result


def test_write_file_rejects_traversal():
    # prompts/output/ 으로 시작하지만 .. 로 탈출 시도
    result = tools.write_file("prompts/output/../../etc/passwd", "x")
    # path traversal 가드에서 거부
    assert "거부" in result


def test_write_file_size_limit():
    huge = "x" * (filesystem.MAX_FILE_BYTES + 1)
    result = tools.write_file("prompts/output/big.txt", huge)
    assert "너무 큼" in result


# ── bash ─────────────────────────────────────────────────────────────────────


@SKIP_ON_WINDOWS
@pytest.mark.asyncio
async def test_bash_allowed_command():
    result = await tools.bash("ls")
    assert "exit=0" in result


@pytest.mark.asyncio
async def test_bash_rejects_disallowed():
    result = await tools.bash("rm -rf /")
    assert "실행 거부" in result
    assert "allowlist" in result


@pytest.mark.asyncio
async def test_bash_rejects_shell_metachars():
    result = await tools.bash("ls; cat /etc/passwd")
    assert "셸 메타문자" in result


@pytest.mark.asyncio
async def test_bash_rejects_pipe():
    result = await tools.bash("ls | grep x")
    assert "셸 메타문자" in result


@pytest.mark.asyncio
async def test_bash_rejects_backtick():
    result = await tools.bash("ls `pwd`")
    assert "셸 메타문자" in result


@pytest.mark.asyncio
async def test_bash_allowlist_prefix_matching():
    # "git status" 는 허용
    result = await tools.bash("git status")
    # cwd 가 git 저장소가 아니더라도 명령 자체는 실행됨 (allowlist 통과)
    assert "exit=" in result


@pytest.mark.asyncio
async def test_bash_prefix_must_be_word_boundary():
    # "lsx" 는 "ls" prefix 로 잘못 통과되면 안 됨
    result = await tools.bash("lsx fake")
    assert "실행 거부" in result


# ── execute 디스패치 ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_unknown_tool():
    result = await tools.execute("nonexistent", {})
    assert "알 수 없는 도구" in result


@pytest.mark.asyncio
async def test_execute_missing_arg():
    result = await tools.execute("read_file", {})
    assert "필수 인자 누락" in result


@pytest.mark.asyncio
async def test_execute_read_file():
    result = await tools.execute("read_file", {"path": "app/main.py"})
    assert "hello" in result
