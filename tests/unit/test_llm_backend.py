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
