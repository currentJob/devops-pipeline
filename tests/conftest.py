"""테스트 전역 픽스처.

app.config 는 import 시점에 TELEGRAM_TOKEN 등을 _require 로 강제한다.
단위 테스트는 실제 토큰이 필요 없으므로, app 모듈을 import 하기 전에
더미 값을 주입한다. 실제 시크릿은 절대 여기에 두지 않는다.
"""

from __future__ import annotations

import os

# setdefault: 실제 환경변수가 이미 있으면 덮어쓰지 않음 (로컬 .env 존중)
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "0")
