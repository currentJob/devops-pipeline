"""CI 스모크 — 워커 /selfcheck 에서 필수 항목(db/git/qdrant) 통과를 확인.

워커 컨테이너 안에서 실행한다(127.0.0.1:8766 접근). 일부 항목(llm 등)은 CI 에 키가
없어 실패할 수 있으므로 전체 ok 가 아니라 '필수 항목'만 검증한다.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

REQUIRED = {"db", "workspace_git", "qdrant"}
URL = "http://127.0.0.1:8766/selfcheck"


def main() -> int:
    try:
        body = urllib.request.urlopen(URL, timeout=10).read()
    except urllib.error.HTTPError as e:  # 503(일부 항목 실패)여도 본문은 읽음
        body = e.read()
    data = json.loads(body)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    bad = [c["name"] for c in data.get("checks", []) if c["name"] in REQUIRED and not c["ok"]]
    if bad:
        print(f"FAILED required checks: {bad}")
        return 1
    print("smoke OK — 필수 항목(db/git/qdrant) 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
