"""Outcome — 에이전트 작업 실행 결과를 나타내는 값 객체(value object).

성공/실패를 결과 문자열의 *모양*(예: 괄호로 감쌈)으로 추론하던 취약한 관례를
대체한다. run_task/run_plan_task 가 이 타입을 반환하고, 워커는 `ok` 로 분기한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Outcome:
    """작업 실행 결과 — 성공 여부(ok)와 사용자에게 전달할 텍스트(text)."""

    ok: bool
    text: str

    @classmethod
    def success(cls, text: str) -> Outcome:
        return cls(True, text)

    @classmethod
    def failure(cls, text: str) -> Outcome:
        return cls(False, text)
