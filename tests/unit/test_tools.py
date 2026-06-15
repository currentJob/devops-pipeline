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
async def test_bash_kills_process_on_timeout(monkeypatch):
    # 타임아웃 시 고아 프로세스가 남지 않도록 kill + wait 가 호출되어야 한다.
    from app.tools import shell

    killed = {"kill": False, "waited": False}

    class _FakeProc:
        returncode = -9

        async def communicate(self):
            return (b"", b"")

        def kill(self):
            killed["kill"] = True

        async def wait(self):
            killed["waited"] = True

    async def _fake_exec(*_a, **_k):
        return _FakeProc()

    async def _fake_wait_for(coro, timeout):
        coro.close()  # 'coroutine never awaited' 경고 방지
        raise TimeoutError

    monkeypatch.setattr(shell.asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(shell.asyncio, "wait_for", _fake_wait_for)

    out = await shell.bash("ls")
    assert "타임아웃" in out
    assert killed["kill"] and killed["waited"]


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


@pytest.mark.asyncio
async def test_execute_offloads_sync_tool_to_thread():
    # 동기 도구(블로킹)는 이벤트 루프가 아닌 워커 스레드에서 실행되어야 한다.
    import threading

    main_ident = threading.get_ident()
    tools._TOOL_HANDLERS["__thread__"] = lambda _a: str(threading.get_ident())
    try:
        out = await tools.execute("__thread__", {})
        assert out != str(main_ident)
    finally:
        del tools._TOOL_HANDLERS["__thread__"]


@pytest.mark.asyncio
async def test_execute_async_tool_awaited_inline():
    # async 도구(bash)는 await 경로로 실행 (allowlist 거부는 subprocess 없이 반환)
    out = await tools.execute("bash", {"command": "rm -rf /"})
    assert "실행 거부" in out


@pytest.mark.asyncio
async def test_execute_trims_long_output():
    # tool-use 루프 컨텍스트 보호: 4000자 초과 결과는 트림
    tools._TOOL_HANDLERS["__big__"] = lambda _a: "x" * 10000
    try:
        out = await tools.execute("__big__", {})
        assert "잘림" in out
        assert len(out) < 10000
    finally:
        del tools._TOOL_HANDLERS["__big__"]
