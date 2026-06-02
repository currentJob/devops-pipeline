"""_vllm_available 폴백 결정 로직 단위 테스트.

실제 LLM/네트워크 호출 없이, vLLM 헬스 프로브가 실패하거나 미설정일 때
False(=Claude API 폴백) 를 반환하는지 검증.
"""

from __future__ import annotations

import aiohttp
import pytest

from app import config
from app.agent import graph


@pytest.fixture(autouse=True)
def _reset_cache():
    graph._vllm_health_cache = None
    yield
    graph._vllm_health_cache = None


async def test_unavailable_when_endpoint_unset(monkeypatch):
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "")
    assert await graph._vllm_available() is False


async def test_unavailable_on_probe_failure(monkeypatch):
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "http://vllm:8000")

    class _BoomSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        def get(self, *_a, **_k):
            raise aiohttp.ClientError("connection refused")

    monkeypatch.setattr(graph.aiohttp, "ClientSession", _BoomSession)
    assert await graph._vllm_available() is False


async def test_probe_result_is_cached(monkeypatch):
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "http://vllm:8000")
    graph._vllm_health_cache = (graph.time.monotonic(), True)

    # 캐시가 유효하면 네트워크 호출 없이 캐시값 반환
    def _boom(*_a, **_k):
        raise AssertionError("캐시 유효 구간에서 프로브가 호출되면 안 됨")

    monkeypatch.setattr(graph.aiohttp, "ClientSession", _boom)
    assert await graph._vllm_available() is True


def test_vllm_max_tokens_capped_to_half_context(monkeypatch):
    # 출력이 컨텍스트를 넘지 않도록 절반으로 캡
    monkeypatch.setattr(config, "WORKER_MAX_TOKENS", 8192)
    monkeypatch.setattr(config, "VLLM_MAX_MODEL_LEN", 8192)
    assert graph._vllm_max_tokens() == 4096

    monkeypatch.setattr(config, "VLLM_MAX_MODEL_LEN", 4096)
    assert graph._vllm_max_tokens() == 2048


def test_vllm_max_tokens_respects_lower_worker_limit(monkeypatch):
    # WORKER_MAX_TOKENS 가 더 작으면 그 값을 따름
    monkeypatch.setattr(config, "WORKER_MAX_TOKENS", 1024)
    monkeypatch.setattr(config, "VLLM_MAX_MODEL_LEN", 8192)
    assert graph._vllm_max_tokens() == 1024


def _patch_backends(monkeypatch, *, vllm_up: bool, claude_key: str):
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "http://vllm:8000")
    monkeypatch.setattr(config, "VLLM_ROUTES_SET", frozenset({"general"}))
    monkeypatch.setattr(config, "CLAUDE_API_KEY", claude_key)

    async def _probe():
        return vllm_up

    monkeypatch.setattr(graph, "_vllm_available", _probe)


async def test_make_llm_vllm_route_uses_vllm(monkeypatch):
    _patch_backends(monkeypatch, vllm_up=True, claude_key="sk-test")
    llm = await graph._make_llm("general")
    assert type(llm).__name__ == "ChatOpenAI"


async def test_make_llm_claude_route_uses_claude(monkeypatch):
    _patch_backends(monkeypatch, vllm_up=True, claude_key="sk-test")
    llm = await graph._make_llm("code")
    assert type(llm).__name__ == "ChatAnthropic"


async def test_make_llm_vllm_route_falls_back_to_claude_when_down(monkeypatch):
    _patch_backends(monkeypatch, vllm_up=False, claude_key="sk-test")
    llm = await graph._make_llm("general")
    assert type(llm).__name__ == "ChatAnthropic"


async def test_make_llm_claude_route_falls_back_to_vllm_without_key(monkeypatch):
    _patch_backends(monkeypatch, vllm_up=True, claude_key="")
    llm = await graph._make_llm("code")
    assert type(llm).__name__ == "ChatOpenAI"


def test_route_backend_label(monkeypatch):
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "http://vllm:8000")
    monkeypatch.setattr(config, "VLLM_ROUTES_SET", frozenset({"general"}))
    assert graph._route_backend_label("general") == "vLLM"
    assert graph._route_backend_label("code") == "Claude"
