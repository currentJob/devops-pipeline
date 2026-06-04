"""tools/notify.py 단위 테스트.

새 인터페이스는 HTTP POST 기반이므로 _post 를 모킹한다.
"""

from __future__ import annotations

import io
import urllib.error

from tools import notify


def test_read_message_from_arg():
    assert notify._read_message("hello") == "hello"


def test_read_message_from_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("from stdin\n"))
    assert notify._read_message("-") == "from stdin"


def test_main_dry_run_succeeds(capsys):
    rc = notify.main(["--dry-run", "테스트 메시지"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "dry-run" in captured.out
    assert "테스트 메시지" in captured.out


def test_main_empty_message_fails():
    rc = notify.main(["--dry-run", ""])
    assert rc == 1


def test_main_http_200_returns_0(monkeypatch):
    monkeypatch.setattr(notify, "_post", lambda url, text, timeout: (200, "ok"))
    rc = notify.main(["메시지"])
    assert rc == 0


def test_main_http_non200_returns_2(monkeypatch, capsys):
    monkeypatch.setattr(notify, "_post", lambda url, text, timeout: (503, "send failed"))
    rc = notify.main(["메시지"])
    assert rc == 2
    assert "HTTP 503" in capsys.readouterr().err


def test_main_url_error_returns_2(monkeypatch, capsys):
    def _raise(url, text, timeout):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(notify, "_post", _raise)
    rc = notify.main(["메시지"])
    assert rc == 2
    assert "연결 오류" in capsys.readouterr().err
