import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum

import anthropic
from telegram.ext import Application

from app import config, notifier

logger = logging.getLogger(__name__)


class StepStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


@dataclass
class PipelineResult:
    step: str
    status: StepStatus
    data: dict = field(default_factory=dict)


# ── Claude 헬퍼 ──────────────────────────────────────────────────────────────


def _claude_client() -> anthropic.Anthropic | None:
    if not config.CLAUDE_API_KEY:
        logger.warning("CLAUDE_API_KEY 미설정 - Claude 기능 비활성화")
        return None
    return anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)


def analyze_with_claude(prompt: str) -> str:
    """Claude로 데이터를 분석하고 요약 텍스트를 반환."""
    client = _claude_client()
    if client is None:
        return "(Claude 미연결 - 분석 생략)"

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system="당신은 자동화 파이프라인의 분석 전문가입니다. 간결하고 명확하게 분석 결과를 제공하세요.",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except anthropic.AuthenticationError:
        logger.warning("Claude API 키 인증 실패 - 분석 건너뜀 (CLAUDE_API_KEY 확인 필요)")
        return "(Claude 인증 실패 - .env의 CLAUDE_API_KEY를 확인하세요)"
    except anthropic.APIError as e:
        logger.warning("Claude API 오류: %s", e)
        return f"(Claude API 오류 - {e})"


# ── 파이프라인 스텝 ──────────────────────────────────────────────────────────


async def step_collect(app: Application) -> PipelineResult:
    """1단계: 데이터 수집 (실제 구현에서는 API 호출, DB 조회 등으로 교체)"""
    logger.info("[1단계] 데이터 수집 시작")

    data = {"items": 150, "total_amount": 2_350_000, "currency": "KRW"}

    await notifier.send_message(app, "📥 *1단계 완료*: 데이터 수집 완료\n항목 수: 150개")
    logger.info("[1단계] 완료: %s", data)
    return PipelineResult(step="collect", status=StepStatus.APPROVED, data=data)


async def step_analyze(app: Application, collected: dict) -> PipelineResult:
    """2단계: Claude로 데이터 분석 후 사용자 승인 요청"""
    logger.info("[2단계] 분석 시작")

    summary = analyze_with_claude(
        f"다음 수집 데이터를 분석하고 처리 진행 여부를 판단해주세요:\n{collected}"
    )

    approved = await notifier.request_approval(
        app=app,
        task_id=str(uuid.uuid4()),
        message=(
            f"📊 *2단계 - 분석 결과 검토*\n\n"
            f"항목 수: {collected['items']}개\n"
            f"총 금액: ₩{collected['total_amount']:,}\n\n"
            f"*AI 분석:*\n{summary}\n\n"
            f"다음 단계(처리 실행)를 진행할까요?"
        ),
    )

    status = StepStatus.APPROVED if approved else StepStatus.REJECTED
    logger.info("[2단계] 사용자 결정: %s", status)
    return PipelineResult(step="analyze", status=status, data={"summary": summary})


async def step_execute(app: Application, analysis: dict) -> PipelineResult:
    """3단계: 실제 처리 실행 (실제 구현에서는 외부 API, DB 업데이트 등으로 교체)"""
    logger.info("[3단계] 실행 시작")

    # 실제 작업 수행 위치
    result = {"processed": True, "message": "작업 완료"}

    await notifier.send_message(app, "✅ *3단계 완료*: 모든 처리가 완료되었습니다.")
    logger.info("[3단계] 완료: %s", result)
    return PipelineResult(step="execute", status=StepStatus.APPROVED, data=result)


# ── 메인 파이프라인 ──────────────────────────────────────────────────────────


async def run(app: Application) -> list[PipelineResult]:
    """전체 파이프라인 실행. 각 단계 결과를 리스트로 반환."""
    results: list[PipelineResult] = []

    await notifier.send_message(app, "🚀 *자동화 파이프라인 시작*")
    logger.info("파이프라인 시작")

    # 1단계: 수집
    r1 = await step_collect(app)
    results.append(r1)

    # 2단계: 분석 + 승인
    r2 = await step_analyze(app, r1.data)
    results.append(r2)

    if r2.status == StepStatus.REJECTED:
        await notifier.send_message(app, "🛑 *파이프라인 중단*: 사용자가 거절했습니다.")
        logger.info("파이프라인 중단 - 사용자 거절")
        return results

    # 3단계: 실행
    r3 = await step_execute(app, r2.data)
    results.append(r3)

    await notifier.send_message(app, "🎉 *파이프라인 완료*: 모든 단계가 성공적으로 완료되었습니다.")
    logger.info("파이프라인 완료")
    return results
