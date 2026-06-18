"""pocsandbox compose config 파싱 — stderr 경고 혼입 회귀.

`docker compose config --format json` 의 JSON(stdout) 뒤에 _run 이 합친 stderr 경고가
붙어도 앞 JSON 만 파싱돼야 한다('Extra data' 실패 방지).
"""

from __future__ import annotations

import json

import pytest

from app.pocsandbox.server import _parse_json_obj


def test_parses_clean_json():
    assert _parse_json_obj('{"services": {"app": {}}}') == {"services": {"app": {}}}


def test_ignores_trailing_stderr_warning():
    # stdout(JSON) + stderr(경고) 가 합쳐진 형태 — 앞 JSON 만 파싱
    out = '{"services": {"app": {"image": "x"}}}\nlevel=warning msg="version is obsolete"\n'
    assert _parse_json_obj(out) == {"services": {"app": {"image": "x"}}}


def test_multiline_json_then_warning():
    out = '{\n  "services": {\n    "app": {}\n  }\n}\ntime="t" level=warning msg="env not set"'
    assert _parse_json_obj(out)["services"] == {"app": {}}


def test_raises_when_no_json_object():
    with pytest.raises(json.JSONDecodeError):
        _parse_json_obj('level=warning msg="no json here"')
