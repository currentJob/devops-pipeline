"""app.clock — 문서 타임스탬프 KST(UTC+9) 고정 검증."""

from __future__ import annotations

from datetime import UTC, datetime

from app import clock


def test_kst_offset_is_plus_9():
    assert clock.KST.utcoffset(None).total_seconds() == 9 * 3600


def test_now_is_kst_aware_and_9h_ahead_of_utc():
    now = clock.now()
    assert now.tzinfo is clock.KST
    utc = datetime.now(UTC)
    # KST 벽시계 = UTC + 9h (같은 순간을 다른 표기로 비교)
    assert abs((now.replace(tzinfo=None) - utc.replace(tzinfo=None)).total_seconds() - 9 * 3600) < 5


def test_today_matches_now_date():
    assert clock.today() == clock.now().date()
