"""문서·노트에 기록하는 시각을 한국 표준시(KST, UTC+9)로 통일.

컨테이너가 UTC 로 동작하므로 `datetime.now()`/`date.today()` 는 UTC 를 반환한다.
한국은 서머타임이 없어 고정 오프셋(+9)으로 충분하다(tzdata 불필요).

작업이력 DB(`app/worker/store.py`)도 KST 로 저장한다(단일 한국 환경, 표기 일관성).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9), "KST")


def now() -> datetime:
    """현재 시각 (KST, tz-aware)."""
    return datetime.now(KST)


def today() -> date:
    """오늘 날짜 (KST 기준)."""
    return now().date()
