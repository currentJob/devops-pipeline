import datetime
import time

import aiohttp
import psutil
from telegram import Update
from telegram.ext import ContextTypes

from app import config
from app.bot.commands import _authorized, _format_uptime, _state


async def cmd_start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(
        "🤖 *자동화 봇 대기 중*\n\n"
        "주요 명령어:\n"
        "`/run` 파이프라인 실행\n"
        "`/task <설명>` 자유형 작업 위임\n"
        "`/status` 서버 상태\n"
        "`/help` 전체 명령어 목록",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(
        "📋 *전체 명령어*\n\n"
        "*기본*\n"
        "`/run` 파이프라인 실행\n"
        "`/task <설명>` 자유형 작업 (워커 위임)\n"
        "`/status` CPU/메모리/디스크\n\n"
        "*전문 Worker*\n"
        "`/code <설명>` 코드 버그·보안·리팩토링 분석\n"
        "`/doc <설명>` README·API 문서·가이드 작성\n"
        "`/infra <설명>` Docker·CI/CD·인프라 설정 분석\n"
        "`/plan <설명>` 복합 작업 분해 후 순차 실행\n\n"
        "*운영*\n"
        "`/uptime` 봇 가동 시간\n"
        "`/health` 봇+워커+Claude API 종합 헬스\n"
        "`/model` 현재 사용 중인 AI 모델\n"
        "`/history` 최근 작업 이력 조회\n\n"
        "*품질 검사 (워커 위임)*\n"
        "`/lint` ruff check 실행\n"
        "`/test` pytest 실행\n"
        "`/audit` pip-audit 실행\n\n"
        "*조회*\n"
        "`/diff` 마지막 커밋 변경 사항\n\n"
        "*Git*\n"
        "`/commit` 변경 내역으로 커밋 메시지 생성 → 확인 후 로컬 커밋\n"
        "`/push` 현재 브랜치를 origin 으로 push (확인 후, GITHUB\\_TOKEN 필요)\n\n"
        "*트렌드 리서치 / 지식*\n"
        "`/stack` IT 트렌드 조사 → 중복 회피 → Obsidian vault 노트 생성\n"
        "`/reindex` vault 노트를 벡터 인덱스에 재인덱싱",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    await update.message.reply_text(
        f"📊 *서버 상태*\n\n"
        f"🕐 시각: {now}\n"
        f"💻 CPU: {cpu}%\n"
        f"🧠 메모리: {mem.percent}% ({mem.used // 1024**2}MB / {mem.total // 1024**2}MB)\n"
        f"💾 디스크: {disk.percent}% 사용 중\n"
        f"⚙️ 파이프라인: {'실행 중' if _state.running else '대기 중'}",
        parse_mode="Markdown",
    )


async def cmd_uptime(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    if _state.start_time is None:
        await update.message.reply_text("⚠️ 시작 시각 미설정")
        return
    elapsed = time.monotonic() - _state.start_time
    await update.message.reply_text(
        f"🕐 *Uptime*: {_format_uptime(elapsed)}",
        parse_mode="Markdown",
    )


async def cmd_model(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(
        f"🤖 *현재 사용 모델*\n\n`{config.WORKER_MODEL}`",
        parse_mode="Markdown",
    )


async def cmd_health(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    worker_ok = False
    worker_detail = ""
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(config.WORKER_HEALTH_URL, timeout=aiohttp.ClientTimeout(total=3)) as resp,
        ):
            worker_ok = resp.status == 200
            if not worker_ok:
                worker_detail = f" (HTTP {resp.status})"
    except aiohttp.ClientError as e:
        worker_detail = f" ({type(e).__name__})"

    claude_ok = bool(config.CLAUDE_API_KEY)

    def m(ok: bool) -> str:
        return "🟢" if ok else "🔴"

    await update.message.reply_text(
        f"🩺 *Health*\n\n"
        f"{m(True)} bot\n"
        f"{m(worker_ok)} worker{worker_detail}\n"
        f"{m(claude_ok)} Claude API key {'설정됨' if claude_ok else '미설정'}",
        parse_mode="Markdown",
    )
