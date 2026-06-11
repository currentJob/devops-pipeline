"""Grafana 프로비저닝 자산(데이터소스·대시보드) 정합성 검증.

JSON/YAML 파싱 오류와 필수 필드 누락을 CI 에서 조기 검출 (Grafana 기동 전).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_DASH_DIR = _ROOT / "monitoring" / "grafana" / "provisioning" / "dashboards"

_dashboards = sorted(_DASH_DIR.glob("*.json"))


def test_dashboard_dir_has_files():
    assert _dashboards, "프로비저닝 대시보드 JSON 이 없음"


@pytest.mark.parametrize("path", _dashboards, ids=lambda p: p.name)
def test_dashboard_valid(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("uid"), f"{path.name}: uid 누락"
    assert data.get("title"), f"{path.name}: title 누락"
    panels = data.get("panels")
    assert isinstance(panels, list) and panels, f"{path.name}: panels 비어 있음"
    for p in panels:
        assert "gridPos" in p, f"{path.name}: 패널 '{p.get('title')}' gridPos 누락"
        if p.get("type") != "row":
            assert p.get("targets"), f"{path.name}: 패널 '{p.get('title')}' targets 누락"


def test_dashboard_uids_unique():
    uids = [json.loads(p.read_text(encoding="utf-8"))["uid"] for p in _dashboards]
    assert len(uids) == len(set(uids)), f"중복 uid: {uids}"
