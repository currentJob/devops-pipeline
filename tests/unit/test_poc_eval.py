"""PoC 평가 파이프라인(app.pipeline.poc_eval) 단위 테스트.

정적지표 측정·소스 다이제스트·LLM JSON 파싱·리포트 렌더·Telegram 요약,
그리고 evaluate() 의 LLM 연결/미연결 두 경로를 검증한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import config
from app.pipeline import poc_eval


def _make_poc(root: Path) -> Path:
    """2개 서비스 구성의 최소 PoC 디렉토리 생성."""
    d = root / "sample-poc"
    (d / "ingest").mkdir(parents=True)
    (d / "query").mkdir()
    (d / "docker-compose.yml").write_text(
        "services:\n  ingest:\n    build: ./ingest\n  query:\n    build: ./query\n",
        encoding="utf-8",
    )
    (d / "ingest" / "main.py").write_text("print('ingest')\nx = 1\n", encoding="utf-8")
    (d / "ingest" / "requirements.txt").write_text("duckdb\n# 주석\nrequests\n\n", encoding="utf-8")
    (d / "ingest" / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (d / "query" / "main.py").write_text("print('query')\n", encoding="utf-8")
    (d / "query" / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (d / "README.md").write_text("# sample\n", encoding="utf-8")
    (d / "HANDOFF.md").write_text("# handoff\n", encoding="utf-8")
    return d


def test_list_pocs(tmp_path):
    assert poc_eval.list_pocs(tmp_path / "missing") == []  # 없으면 빈 목록
    _make_poc(tmp_path)
    (tmp_path / "sample-poc" / poc_eval.REPORT_NAME).write_text("# 평가\n", encoding="utf-8")
    (tmp_path / "not-a-slug!").mkdir()  # 잘못된 slug 디렉토리는 제외
    rows = poc_eval.list_pocs(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["slug"] == "sample-poc"
    assert row["has_eval"] and row["has_handoff"] and row["has_compose"]
    assert row["file_count"] == poc_eval.collect_metrics(tmp_path / "sample-poc")["file_count"]


def test_valid_slug():
    assert poc_eval.valid_slug("duckdb-mcp-pipeline")
    assert not poc_eval.valid_slug("../etc")
    assert not poc_eval.valid_slug("")


def test_collect_metrics(tmp_path):
    m = poc_eval.collect_metrics(_make_poc(tmp_path))
    assert m["services"] == 2
    assert m["dockerfiles"] == 2
    assert m["dependencies"] == 2  # duckdb, requests (주석·빈 줄 제외)
    assert m["has_readme"] and m["has_handoff"] and m["has_compose"]
    assert m["languages"]["Python"] == 3  # 2 + 1 LOC
    assert m["total_loc"] > 0


def test_collect_metrics_excludes_own_report(tmp_path):
    d = _make_poc(tmp_path)
    before = poc_eval.collect_metrics(d)["file_count"]
    (d / poc_eval.REPORT_NAME).write_text("# 이전 평가\n", encoding="utf-8")
    after = poc_eval.collect_metrics(d)["file_count"]
    assert before == after  # EVALUATION.md 는 지표에서 제외


def test_read_sources_has_headers_and_cap(tmp_path):
    d = _make_poc(tmp_path)
    src = poc_eval.read_sources(d, cap=10_000)
    assert "ingest/main.py" in src and "print('ingest')" in src
    tiny = poc_eval.read_sources(d, cap=50)
    assert len(tiny) < 400  # 상한 도달 시 조기 종료


@pytest.mark.parametrize(
    "raw,expected_has",
    [
        ('{"summary": "ok", "scores": {}}', True),
        ('```json\n{"summary": "x"}\n```', True),
        ('설명...\n{"summary": "y"}\n뒤 잡설', True),
        ("no json here", False),
    ],
)
def test_parse_llm_json(raw, expected_has):
    assert bool(poc_eval.parse_llm_json(raw)) is expected_has


def test_scores_and_overall():
    parsed = {"scores": {"functionality": 4, "security": 2, "bogus": 9, "code_quality": 3}}
    scores = poc_eval._scores_from(parsed)
    assert scores == {"기능성·완성도": 4, "보안": 2, "코드 품질": 3}  # 범위 밖/미정의 키 제외
    assert poc_eval._overall(scores) == 3.0
    assert poc_eval._overall({}) is None


def test_render_report_sections(tmp_path):
    m = poc_eval.collect_metrics(_make_poc(tmp_path))
    parsed = {
        "what": "DuckDB 적재 코드",
        "where": "데이터 파이프라인",
        "strengths": ["가볍다"],
        "pros": ["단순"],
        "cons": ["테스트 없음"],
        "scores": {k: 4 for k, _ in poc_eval.RUBRIC},
        "summary": "전반적으로 양호",
    }
    report = poc_eval.render_report("sample-poc", m, {"ok": True, "stage": "run"}, parsed, True)
    for section in [
        "## 종합",
        "## 관점별 점수",
        "## 정적 지표",
        "## 무슨 코드인가",
        "## 단점·리스크",
    ]:
        assert section in report
    assert "DuckDB 적재 코드" in report and "전반적으로 양호" in report


def test_render_report_llm_missing(tmp_path):
    m = poc_eval.collect_metrics(_make_poc(tmp_path))
    report = poc_eval.render_report("sample-poc", m, {"ok": None, "stage": "-"}, {}, False)
    assert "LLM 미연결" in report


def test_format_telegram_summary():
    out = poc_eval.format_telegram_summary(
        {
            "slug": "p",
            "overall": 3.3,
            "scores": {"보안": 2},
            "summary": "총평",
            "report_path": "prompts/output/poc/p/EVALUATION.md",
        }
    )
    assert "3.3/5" in out and "보안: 2" in out and "EVALUATION.md" in out


async def test_evaluate_without_llm_writes_metrics_report(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CLAUDE_API_KEY", "")
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "")
    d = _make_poc(tmp_path)
    result = await poc_eval.evaluate(d, "sample-poc", {"ok": True, "stage": "run", "logs": "hi"})
    assert result["llm_ok"] is False
    assert result["overall"] is None
    assert (d / poc_eval.REPORT_NAME).is_file()
    assert result["metrics"]["services"] == 2


async def test_evaluate_with_mocked_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CLAUDE_API_KEY", "x")
    monkeypatch.setattr(config, "VLLM_ENDPOINT", "")
    from app.agent import runtime

    async def fake_chat(system, user, route=None):
        return (
            '{"what":"코드","where":"x","strengths":["s"],"pros":["p"],"cons":["c"],'
            '"scores":{"functionality":5,"code_quality":4,"security":3,'
            '"maintainability":4,"dependencies":4,"runnability":2,"documentation":5},'
            '"summary":"총평"}'
        )

    monkeypatch.setattr(runtime, "chat", fake_chat)
    d = _make_poc(tmp_path)
    result = await poc_eval.evaluate(d, "sample-poc", {"ok": False, "stage": "run", "logs": "x"})
    assert result["llm_ok"] is True
    assert result["overall"] == pytest.approx(3.9)  # (5+4+3+4+4+2+5)/7
    assert result["scores"]["실행 가능성"] == 2
    assert "총평" in (d / poc_eval.REPORT_NAME).read_text(encoding="utf-8")
