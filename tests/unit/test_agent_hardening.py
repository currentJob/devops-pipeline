"""에이전트 견고화 — RAG 조건화 단위 테스트."""

from __future__ import annotations

from app.agent import graph


async def test_retrieve_skips_rag_for_code_task(monkeypatch):
    called = False

    async def fake_retrieve(_q):
        nonlocal called
        called = True
        return "CTX"

    monkeypatch.setattr(graph, "retrieve_context", fake_retrieve)
    out = await graph._retrieve("[CODE_TASK] 설치 패키지 목록")
    assert out == ""
    assert called is False


async def test_retrieve_runs_rag_for_general(monkeypatch):
    async def fake_retrieve(_q):
        return "CTX"

    monkeypatch.setattr(graph, "retrieve_context", fake_retrieve)
    out = await graph._retrieve("최신 IT 트렌드 알려줘")
    assert out == "CTX"
