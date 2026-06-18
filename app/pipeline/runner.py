import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum

import aiohttp
from telegram.ext import Application

from app import config
from app.agent import runtime
from app.bot import notifier
from app.pipeline import security_audit

logger = logging.getLogger(__name__)

_ANALYST_SYSTEM = (
    "당신은 자동화 파이프라인의 분석 전문가입니다. 간결하고 명확하게 분석 결과를 제공하세요."
)


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


async def analyze_with_llm(prompt: str) -> str:
    """통합 런타임(runtime.chat)으로 분석 요약을 반환 — Claude/vLLM 자동 선택·폴백.

    미연결/호출 실패 시에도 파이프라인이 진행되도록 안내 문자열로 graceful 폴백한다.
    """
    if not (config.CLAUDE_API_KEY or config.VLLM_ENDPOINT):
        return "(LLM 미연결 - 분석 생략)"
    try:
        return await runtime.chat(system=_ANALYST_SYSTEM, user=prompt)
    except Exception as e:  # noqa: BLE001 — LLM 실패해도 감사 결과·리포트는 유효
        logger.warning("보안 분석 LLM 호출 실패: %s", e)
        return f"(LLM 분석 실패 - {type(e).__name__})"


async def step_collect(app: Application) -> PipelineResult:
    """1단계: 설치 의존성 인벤토리 수집 + OSV 취약점 스캔."""
    logger.info("[1단계] 의존성 보안 감사 — 패키지 수집 시작")

    packages = security_audit.list_installed_packages()
    await notifier.send_message(
        app, f"📥 *1단계*: 설치 패키지 {len(packages)}개 수집 — OSV 취약점 스캔 중..."
    )

    try:
        audit = await security_audit.scan(packages)
    except aiohttp.ClientError as e:
        logger.warning("OSV 스캔 실패: %s", e)
        await notifier.send_message(app, f"🔴 *1단계 실패*: OSV 스캔 오류 — {e}")
        return PipelineResult(step="collect", status=StepStatus.REJECTED, data={})

    await notifier.send_message(
        app,
        f"📥 *1단계 완료*: {audit['scanned']}개 중 "
        f"*{audit['vulnerable_count']}개* 취약 패키지 발견",
    )
    logger.info(
        "[1단계] 완료: scanned=%d vulnerable=%d", audit["scanned"], audit["vulnerable_count"]
    )
    return PipelineResult(step="collect", status=StepStatus.APPROVED, data=audit)


async def step_analyze(app: Application, audit: dict) -> PipelineResult:
    """2단계: Claude로 취약점 우선순위·교정안 분석 후 사용자 승인 요청."""
    logger.info("[2단계] 취약점 분석 시작")

    findings = security_audit.build_findings_text(audit)
    prompt = (
        "다음은 의존성 취약점 스캔(OSV) 결과입니다. DevSecOps 관점에서 간결한 한국어 "
        "마크다운으로 정리하세요:\n"
        "1) 심각도순 우선순위 (CVSS 기준)\n"
        "2) 각 취약점의 권장 조치 (업그레이드 대상 버전)\n"
        "3) 업그레이드 시 호환성 리스크 간단 평가\n\n"
        f"{findings}"
    )
    summary = await analyze_with_llm(prompt)

    approved = await notifier.request_approval(
        app=app,
        task_id=str(uuid.uuid4()),
        message=(
            f"🛡️ *2단계 — 보안 감사 결과 검토*\n\n"
            f"취약 패키지: *{audit['vulnerable_count']}*개 / 스캔 {audit['scanned']}개\n\n"
            f"*AI 분석:*\n{summary[:2500]}\n\n"
            f"교정 리포트를 생성하고 저장할까요?"
        ),
    )

    status = StepStatus.APPROVED if approved else StepStatus.REJECTED
    logger.info("[2단계] 사용자 결정: %s", status)
    return PipelineResult(step="analyze", status=status, data={"summary": summary})


async def step_execute(app: Application, audit: dict, analysis: dict) -> PipelineResult:
    """3단계: 교정 리포트 생성 → 파일 저장."""
    logger.info("[3단계] 교정 리포트 생성")

    report = security_audit.build_report_markdown(audit, analysis["summary"])
    saved_path = security_audit.save_report(report)

    msg = f"✅ *3단계 완료*: 교정 리포트 생성\n📄 `{saved_path}`"
    await notifier.send_message(app, msg)
    logger.info("[3단계] 완료: path=%s", saved_path)
    return PipelineResult(
        step="execute",
        status=StepStatus.APPROVED,
        data={"report_path": saved_path},
    )


async def run(app: Application) -> list[PipelineResult]:
    """전체 파이프라인 실행 (의존성 보안 감사). 각 단계 결과를 리스트로 반환."""
    results: list[PipelineResult] = []

    await notifier.send_message(app, "🚀 *의존성 보안 감사 파이프라인 시작*")
    logger.info("파이프라인 시작")

    r1 = await step_collect(app)
    results.append(r1)
    if r1.status == StepStatus.REJECTED:  # 스캔 실패
        return results

    audit = r1.data
    if audit.get("vulnerable_count", 0) == 0:
        await notifier.send_message(app, "✅ *취약점 0건* — 모든 의존성이 안전합니다.")
        logger.info("파이프라인 종료 - 취약점 없음")
        return results

    r2 = await step_analyze(app, audit)
    results.append(r2)
    if r2.status == StepStatus.REJECTED:
        await notifier.send_message(app, "🛑 *파이프라인 중단*: 교정을 보류했습니다.")
        logger.info("파이프라인 중단 - 사용자 보류")
        return results

    r3 = await step_execute(app, audit, r2.data)
    results.append(r3)

    await notifier.send_message(app, "🎉 *파이프라인 완료*: 교정 리포트가 생성되었습니다.")
    logger.info("파이프라인 완료")
    return results
