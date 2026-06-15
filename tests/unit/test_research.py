"""recent_research (last30days CLI 래퍼) 단위 테스트.

subprocess 를 모킹하여 네트워크/외부 스크립트 없이 가드·파싱 분기를 검증.
"""

from __future__ import annotations

import pytest

from app import config
from app.tools import research


class _FakeProc:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


@pytest.fixture(autouse=True)
def _enable_research(monkeypatch):
    """기본적으로 활성화 + 실제 vendored 스크립트 경로를 사용하도록 보장."""
    monkeypatch.setattr(config, "RESEARCH_ENABLED", True)
    monkeypatch.setattr(config, "RESEARCH_SCRIPT", "")
    monkeypatch.setattr(config, "RESEARCH_SOURCES", "reddit,hackernews")
    monkeypatch.setattr(config, "RESEARCH_DAYS", 30)
    monkeypatch.setattr(config, "RESEARCH_TIMEOUT_S", 5.0)


def _patch_exec(monkeypatch, proc=None, exc=None):
    async def _fake_exec(*_args, **_kwargs):
        if exc is not None:
            raise exc
        return proc

    monkeypatch.setattr(research.asyncio, "create_subprocess_exec", _fake_exec)


# ── 가드 분기 ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disabled(monkeypatch):
    monkeypatch.setattr(config, "RESEARCH_ENABLED", False)
    result = await research.recent_research("rust async")
    assert "비활성화" in result


@pytest.mark.asyncio
async def test_empty_topic():
    result = await research.recent_research("   ")
    assert "거부" in result


@pytest.mark.asyncio
async def test_topic_too_long():
    result = await research.recent_research("x" * 301)
    assert "너무 김" in result


@pytest.mark.asyncio
async def test_missing_script(monkeypatch):
    monkeypatch.setattr(config, "RESEARCH_SCRIPT", "/nonexistent/last30days.py")
    result = await research.recent_research("kubernetes operators")
    assert "미설치" in result


# ── 실행 분기 (subprocess 모킹) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_success(monkeypatch):
    _patch_exec(monkeypatch, proc=_FakeProc(b"Topic: rust\nTop clusters:\n- ...", returncode=0))
    result = await research.recent_research("rust async")
    assert "Top clusters" in result


@pytest.mark.asyncio
async def test_output_trimmed(monkeypatch):
    big = ("a" * (research._RESULT_MAX_CHARS + 100)).encode()
    _patch_exec(monkeypatch, proc=_FakeProc(big, returncode=0))
    result = await research.recent_research("rust async")
    assert "잘림" in result
    assert len(result) <= research._RESULT_MAX_CHARS + 50


@pytest.mark.asyncio
async def test_empty_output(monkeypatch):
    _patch_exec(monkeypatch, proc=_FakeProc(b"   ", returncode=0))
    result = await research.recent_research("rust async")
    assert "결과 없음" in result


@pytest.mark.asyncio
async def test_nonzero_exit(monkeypatch):
    _patch_exec(monkeypatch, proc=_FakeProc(b"", stderr=b"boom", returncode=1))
    result = await research.recent_research("rust async")
    assert "조사 실패" in result
    assert "boom" in result


@pytest.mark.asyncio
async def test_timeout(monkeypatch):
    # 타임아웃은 wait_for 에서 발생 — 고아 프로세스를 막기 위해 kill 이 호출되어야 한다.
    killed = {"kill": False}

    class _KillProc(_FakeProc):
        def kill(self):
            killed["kill"] = True

        async def wait(self):
            pass

    _patch_exec(monkeypatch, proc=_KillProc(b""))

    async def _fake_wait_for(coro, timeout):
        coro.close()  # 'coroutine never awaited' 경고 방지
        raise TimeoutError

    monkeypatch.setattr(research.asyncio, "wait_for", _fake_wait_for)
    result = await research.recent_research("rust async")
    assert "타임아웃" in result
    assert killed["kill"]


@pytest.mark.asyncio
async def test_oserror(monkeypatch):
    _patch_exec(monkeypatch, exc=OSError("no python"))
    result = await research.recent_research("rust async")
    assert "실행 실패" in result
