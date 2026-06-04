"""작업 완료 텔레그램 알림 CLI.

봇 컨테이너의 HTTP 엔드포인트(localhost:8765/notify)로 메시지를 POST 한다.
stdlib 만 사용 — 호스트에 별도 의존성 불필요.

사용:
    python tools/notify.py "메시지 내용"
    python tools/notify.py --dry-run "메시지 내용"
    echo "메시지" | python tools/notify.py -

종료 코드:
    0  전송 성공 (또는 dry-run 성공)
    1  사용법 오류 / 빈 메시지
    2  HTTP 호출 실패 / 봇 미응답 / 비-200 응답
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("NOTIFY_URL", "http://127.0.0.1:8765/notify")
TIMEOUT_S = float(os.environ.get("NOTIFY_TIMEOUT", "5"))


def _read_message(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read().strip()
    return arg


def _post(url: str, text: str, timeout: float) -> tuple[int, str]:
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.notify",
        description="작업 완료 시 봇 컨테이너의 HTTP 엔드포인트로 텔레그램 알림 요청",
    )
    parser.add_argument("message", help='메시지. "-" 면 stdin 에서 읽음')
    parser.add_argument("--dry-run", action="store_true", help="실제 호출 없이 stdout 출력")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"알림 엔드포인트 (기본 {DEFAULT_URL})")
    args = parser.parse_args(argv)

    text = _read_message(args.message)
    if not text:
        print("빈 메시지", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[dry-run] url={args.url} text={text!r}")
        return 0

    try:
        status, body = _post(args.url, text, TIMEOUT_S)
    except urllib.error.URLError as e:
        print(f"전송 실패 (연결 오류): {e.reason}", file=sys.stderr)
        return 2
    except TimeoutError:
        print(f"전송 실패 (타임아웃 {TIMEOUT_S}s)", file=sys.stderr)
        return 2

    if status != 200:
        print(f"HTTP {status}: {body}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
