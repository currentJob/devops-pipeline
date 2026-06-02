"""security_audit 순수 헬퍼 단위 테스트 (네트워크 불필요)."""

from __future__ import annotations

from app.pipeline import security_audit


def test_list_installed_packages_returns_name_version():
    pkgs = security_audit.list_installed_packages()
    assert pkgs, "설치 패키지가 비어있을 수 없음"
    sample = pkgs[0]
    assert set(sample) == {"name", "version"}
    assert sample["name"] == sample["name"].lower()


def test_summarize_vuln_extracts_fixed_and_severity():
    osv = {
        "id": "GHSA-xxxx",
        "summary": "예시 취약점",
        "severity": [{"type": "CVSS_V3", "score": "9.8"}],
        "affected": [
            {"ranges": [{"events": [{"introduced": "0"}, {"fixed": "2.3.1"}]}]},
        ],
    }
    out = security_audit._summarize_vuln(osv)
    assert out["id"] == "GHSA-xxxx"
    assert out["severity"] == "9.8"
    assert out["fixed"] == ["2.3.1"]
    assert "예시" in out["summary"]


def _sample_audit() -> dict:
    return {
        "scanned": 50,
        "vulnerable_count": 1,
        "vulnerable": [{"name": "flask", "version": "2.0.0", "vuln_ids": ["GHSA-xxxx"]}],
        "vuln_details": {
            "GHSA-xxxx": {
                "id": "GHSA-xxxx",
                "summary": "예시 취약점",
                "severity": "9.8",
                "fixed": ["2.3.1"],
            }
        },
        "truncated": False,
    }


def test_build_findings_text_lists_package_and_vuln():
    text = security_audit.build_findings_text(_sample_audit())
    assert "flask 2.0.0" in text
    assert "GHSA-xxxx" in text
    assert "2.3.1" in text


def test_build_report_markdown_has_sections():
    report = security_audit.build_report_markdown(_sample_audit(), "AI 분석 내용")
    assert report.startswith("# 의존성 보안 감사 리포트")
    assert "## AI 분석 및 권장 조치" in report
    assert "AI 분석 내용" in report
