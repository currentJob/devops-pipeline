"""에이전트 견고화 — RAG 조건화 + 도구 결과 트리밍 단위 테스트."""

from __future__ import annotations

from app.agent import graph, tools


def test_trim_caps_long_output():
    out = tools._trim("x" * 10000)
    assert len(out) < 10000
    assert "잘림" in out


def test_trim_passes_short_output():
    assert tools._trim("ok") == "ok"


async def test_retrieve_skips_rag_for_code_task(monkeypatch):
    called = False

    async def fake_retrieve(_q):
        nonlocal called
        called = True
        return "CTX"

    monkeypatch.setattr(graph, "retrieve_context", fake_retrieve)
    state = {
        "task_id": "t",
        "description": "[CODE_TASK] 설치 패키지 목록",
        "rag_context": "",
        "route": "",
        "result": "",
    }
    out = await graph._retrieve_node(state)
    assert out["rag_context"] == ""
    assert called is False


async def test_retrieve_runs_rag_for_general(monkeypatch):
    async def fake_retrieve(_q):
        return "CTX"

    monkeypatch.setattr(graph, "retrieve_context", fake_retrieve)
    state = {
        "task_id": "t",
        "description": "최신 IT 트렌드 알려줘",
        "rag_context": "",
        "route": "",
        "result": "",
    }
    out = await graph._retrieve_node(state)
    assert out["rag_context"] == "CTX"
