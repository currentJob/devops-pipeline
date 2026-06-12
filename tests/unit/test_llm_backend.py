"""백엔드 선택/폴백 로직 단위 테스트 (app.agent.runtime).

실제 LLM/네트워크 호출 없이, vLLM 헬스 프로브 결과에 따라 select_backend 가
'vllm' / 'claude' 를 올바르게 고르는지 검증.
"""

from __future__ import annotations

import aiohttp
import pytest

from app import config
from app.agent import runtime


@pytest.fixture(autouse=True)
def _reset_cache():
    runtime._vllm_health_cache = None
    yield
    runtime._vllm_health_cache = None


async def test_unavailable_when_endpoint_unset(monkeypatch):
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "")
    assert await runtime._vllm_available() is False


async def test_unavailable_on_probe_failure(monkeypatch):
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "http://vllm:8000")

    class _BoomSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        def get(self, *_a, **_k):
            raise aiohttp.ClientError("connection refused")

    monkeypatch.setattr(runtime.aiohttp, "ClientSession", _BoomSession)
    assert await runtime._vllm_available() is False


async def test_probe_result_is_cached(monkeypatch):
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "http://vllm:8000")
    runtime._vllm_health_cache = (runtime.time.monotonic(), True)

    def _boom(*_a, **_k):
        raise AssertionError("캐시 유효 구간에서 프로브가 호출되면 안 됨")

    monkeypatch.setattr(runtime.aiohttp, "ClientSession", _boom)
    assert await runtime._vllm_available() is True


def test_vllm_max_tokens_capped_to_half_context(monkeypatch):
    monkeypatch.setattr(config, "WORKER_MAX_TOKENS", 8192)
    monkeypatch.setattr(config, "VLLM_MAX_MODEL_LEN", 8192)
    assert runtime._vllm_max_tokens() == 4096

    monkeypatch.setattr(config, "VLLM_MAX_MODEL_LEN", 4096)
    assert runtime._vllm_max_tokens() == 2048


def test_vllm_max_tokens_respects_lower_worker_limit(monkeypatch):
    monkeypatch.setattr(config, "WORKER_MAX_TOKENS", 1024)
    monkeypatch.setattr(config, "VLLM_MAX_MODEL_LEN", 8192)
    assert runtime._vllm_max_tokens() == 1024


def _patch_backends(monkeypatch, *, vllm_up: bool, claude_key: str):
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "http://vllm:8000")
    monkeypatch.setattr(config, "VLLM_ROUTES_SET", frozenset({"general"}))
    monkeypatch.setattr(config, "CLAUDE_API_KEY", claude_key)

    async def _probe():
        return vllm_up

    monkeypatch.setattr(runtime, "_vllm_available", _probe)


async def test_vllm_route_uses_vllm(monkeypatch):
    _patch_backends(monkeypatch, vllm_up=True, claude_key="sk-test")
    assert await runtime.select_backend("general") == "vllm"


async def test_claude_route_uses_claude(monkeypatch):
    _patch_backends(monkeypatch, vllm_up=True, claude_key="sk-test")
    assert await runtime.select_backend("code") == "claude"


async def test_vllm_route_falls_back_to_claude_when_down(monkeypatch):
    _patch_backends(monkeypatch, vllm_up=False, claude_key="sk-test")
    assert await runtime.select_backend("general") == "claude"


async def test_claude_route_falls_back_to_vllm_without_key(monkeypatch):
    _patch_backends(monkeypatch, vllm_up=True, claude_key="")
    assert await runtime.select_backend("code") == "vllm"


def test_route_backend_label(monkeypatch):
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "http://vllm:8000")
    monkeypatch.setattr(config, "VLLM_ROUTES_SET", frozenset({"general"}))
    assert runtime._route_backend_label("general") == "vLLM"
    assert runtime._route_backend_label("code") == "Claude"
