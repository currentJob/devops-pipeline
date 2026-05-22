import asyncio
import datetime
import logging
import os
import time
import uuid

import aiohttp
import psutil
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app import config, notifier, notion_client, pipeline

WORKER_URL = os.environ.get("WORKER_URL", "http://worker:8766/run")
WORKER_HEALTH_URL = os.environ.get("WORKER_HEALTH_URL", "http://worker:8766/health")

logger = logging.getLogger(__name__)

# 파이프라인이 이미 실행 중인지 중복 방지
_running = False
# 봇 시작 시각 (register_commands 호출 시점에 설정)
_start_time: float | None = None


def _authorized(update: Update) -> bool:
    """등록된 chat_id 에서만 명령 허용"""
    return update.effective_chat.id == config.TELEGRAM_CHAT_ID


def _format_uptime(seconds: float) -> str:
    """초 → '2시간 30분 5초' 같은 사람용 문자열."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    parts: list[str] = []
    if h:
        parts.append(f"{h}시간")
    if m:
        parts.append(f"{m}분")
    parts.append(f"{s}초")
    return " ".join(parts)


# ── 워커 위임 헬퍼 ───────────────────────────────────────────────────────────


async def _dispatch_to_worker(update: Update, description: str) -> None:
    """공통 패턴: 워커에 작업 위임 + 즉시 '작업 시작' 응답."""
    task_id = str(uuid.uuid4())[:8]
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                WORKER_URL,
                json={"task_id": task_id, "description": description},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp,
        ):
            if resp.status != 202:
                body = await resp.text()
                await update.message.reply_text(
                    f"⚠️ 워커 응답: {resp.status}\n{body}",
                )
                return
    except aiohttp.ClientError as e:
        logger.warning("워커 통신 실패 task_id=%s: %s", task_id, e)
        await update.message.reply_text(f"🔴 워커 통신 실패: {e}")
        return

    await update.message.reply_text(
        f"🚀 *작업 시작* (id=`{task_id}`)\n\n처리 후 알림 드립니다.",
        parse_mode="Markdown",
    )


# ── 기본 명령 ────────────────────────────────────────────────────────────────


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
        "*운영*\n"
        "`/uptime` 봇 가동 시간\n"
        "`/health` 봇+워커+Claude API 종합 헬스\n\n"
        "*품질 검사 (워커 위임)*\n"
        "`/lint` ruff check 실행\n"
        "`/test` pytest 실행\n"
        "`/audit` pip-audit 실행\n\n"
        "*조회*\n"
        "`/diff` 마지막 커밋 변경 사항\n\n"
        "*트렌드 리서치*\n"
        "`/stack` IT 트렌드 조사 → 중복 회피 → Notion 새 페이지 생성\n"
        "`/notion` Notion 통합 설정 + 연결 상태 진단",
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
        f"⚙️ 파이프라인: {'실행 중' if _running else '대기 중'}",
        parse_mode="Markdown",
    )


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    global _running
    if _running:
        await update.message.reply_text("⚠️ 파이프라인이 이미 실행 중입니다.")
        return

    await update.message.reply_text("▶️ 파이프라인을 시작합니다...")
    asyncio.create_task(_run_pipeline(context.application))


async def _run_pipeline(app: Application) -> None:
    global _running
    _running = True
    try:
        await pipeline.run(app)
    except Exception:
        logger.exception("파이프라인 오류")
        await notifier.send_message(app, "🔴 *오류*: 파이프라인이 예기치 않게 종료되었습니다.")
    finally:
        _running = False


async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/task <설명>` — 자유형 작업 위임."""
    if not _authorized(update):
        return

    description = " ".join(context.args).strip()
    if not description:
        await update.message.reply_text(
            "사용법: `/task <작업 설명>`\n예: `/task .env 보호 방법 요약해줘`",
            parse_mode="Markdown",
        )
        return

    await _dispatch_to_worker(update, description)


# ── 운영 ─────────────────────────────────────────────────────────────────────


async def cmd_uptime(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    if _start_time is None:
        await update.message.reply_text("⚠️ 시작 시각 미설정")
        return
    elapsed = time.monotonic() - _start_time
    await update.message.reply_text(
        f"🕐 *Uptime*: {_format_uptime(elapsed)}",
        parse_mode="Markdown",
    )


async def cmd_health(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    # 워커 헬스
    worker_ok = False
    worker_detail = ""
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(WORKER_HEALTH_URL, timeout=aiohttp.ClientTimeout(total=3)) as resp,
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


# ── 품질 검사 (워커 위임) ────────────────────────────────────────────────────


async def cmd_lint(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await _dispatch_to_worker(
        update,
        "bash 도구로 'uv run ruff check .' 를 실행하고 결과를 한국어로 보고해줘. "
        "0 errors 면 '✅ ruff 통과' 만 답해. 오류가 있으면 파일+규칙ID+간단 설명만 표로 정리.",
    )


async def cmd_test(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await _dispatch_to_worker(
        update,
        "bash 도구로 'uv run pytest tests/ -v' 를 실행하고, 통과/실패 개수만 우선 보고해. "
        "실패가 있으면 어떤 케이스가 왜 실패했는지 한 줄씩만.",
    )


async def cmd_audit(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await _dispatch_to_worker(
        update,
        "bash 도구로 'uv run pip-audit' 를 실행하고, CVE 가 있으면 "
        "패키지+CVE-ID+심각도만 표로 한국어 정리. 없으면 '✅ CVE 0건' 만 답해.",
    )


# ── 조회 ─────────────────────────────────────────────────────────────────────


async def cmd_diff(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await _dispatch_to_worker(
        update,
        "bash 도구로 다음을 순서대로 실행하고 결과를 합쳐서 보고해줘:\n"
        "1) 'git log -1 --oneline' — 마지막 커밋 한 줄\n"
        "2) 'git diff HEAD~1 --stat' — 변경 통계\n"
        "한국어 요약만 1~2문장 추가하고, 출력은 그대로 인용.",
    )


async def cmd_notion(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/notion` — Notion 통합 설정 + 연결 상태 진단."""
    if not _authorized(update):
        return

    def m(ok: bool) -> str:
        return "🟢" if ok else "🔴"

    token = config.NOTION_TOKEN
    page_id = config.NOTION_PARENT_PAGE_ID

    token_set = bool(token)
    page_id_set = bool(page_id)

    if not token_set or not page_id_set:
        lines = [
            "🔍 *Notion 연결 상태*\n",
            f"{m(token_set)} NOTION\\_TOKEN {'설정됨' if token_set else '미설정 — .env 에 추가 필요'}",
            f"{m(page_id_set)} NOTION\\_PARENT\\_PAGE\\_ID {'설정됨' if page_id_set else '미설정 — .env 에 추가 필요'}",
        ]
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    await update.message.reply_text("🔍 Notion API 연결 확인 중...", parse_mode="Markdown")

    result = await notion_client.check_connection(token, page_id)

    lines = [
        "🔍 *Notion 연결 상태*\n",
        "🟢 NOTION\\_TOKEN 설정됨",
        "🟢 NOTION\\_PARENT\\_PAGE\\_ID 설정됨",
        f"{m(result['token_ok'])} API 토큰 유효성",
        f"{m(result['page_ok'])} 부모 페이지 접근 권한",
    ]
    if result["error"]:
        lines.append(f"\n⚠️ {result['error']}")
    else:
        lines.append("\n✅ 모든 설정 정상 — `/stack` 사용 가능")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_stack(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/stack` — IT 트렌드를 조사해서 Notion 에 새 페이지 생성. 중복 회피."""
    if not _authorized(update):
        return
    await _dispatch_to_worker(
        update,
        "[STACK_TASK] 다음 절차를 정확히 따라 실행해라.\n\n"
        "1. notion_search 도구로 다음 4가지 쿼리를 차례로 호출해 기존 페이지 제목을 수집:\n"
        "   - 'IT 트렌드'\n"
        "   - 'tech stack'\n"
        "   - '학습 로드맵'\n"
        "   - 'technology'\n"
        "2. 검색 결과의 제목들에서 이미 다뤄진 카테고리를 추정 (예: AI 에이전트, "
        "WebAssembly, Iceberg, DevOps, 보안 등). 정확히 매칭되는 카테고리만 '다뤄짐' 으로 분류.\n"
        "3. 다뤄지지 않았거나 보강할 만한 **신규 카테고리 3~5개** 를 선정. 예시 후보군:\n"
        "   - Mojo/Zig (신흥 시스템 언어)\n"
        "   - Tauri/Wails (네이티브 데스크톱)\n"
        "   - Local-First 데이터 (CRDT, Automerge, Yjs)\n"
        "   - Edge AI/추론 (Cloudflare Workers AI, Vercel AI SDK)\n"
        "   - DuckDB·OLAP 임베디드\n"
        "   - HTMX/Hyperscript (HTML-driven 프론트)\n"
        "   - Bazel/Nx (모노레포 빌드)\n"
        "   - WebGPU\n"
        "   - 실시간 협업 (Liveblocks, PartyKit)\n"
        "   * 위는 예시일 뿐 — 다른 트렌드도 좋음. 기존과 겹치지 않으면 OK.\n"
        "4. 선정한 각 카테고리에 대해 마크다운 섹션을 작성:\n"
        "   - ## 카테고리명\n"
        "   - ### 트렌드 개요 (2~4문장)\n"
        "   - ### 핵심 기술 스택 (불릿)\n"
        "   - ### 추천 학습 자료 (가능하면 알고 있는 공식 문서/주요 블로그 링크)\n"
        "   - ### 적합한 역할\n"
        "5. 본문 맨 앞에 짧은 서론(왜 이 신규 트렌드들인지) + 맨 뒤에 '우선순위 추천' 짧게.\n"
        "6. notion_create_page 호출:\n"
        "   - title: '2026 신규 트렌드 — <오늘 날짜 YYYY-MM-DD>'\n"
        "   - content: 위 마크다운\n"
        "   - icon: '🆕'\n"
        "7. 응답: 생성된 페이지 url 만 한 줄로 알려줘. 추가 설명 불필요.",
    )


# ── 등록 ─────────────────────────────────────────────────────────────────────


def register_commands(app: Application) -> None:
    global _start_time
    _start_time = time.monotonic()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("task", cmd_task))
    app.add_handler(CommandHandler("uptime", cmd_uptime))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("lint", cmd_lint))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("audit", cmd_audit))
    app.add_handler(CommandHandler("diff", cmd_diff))
    app.add_handler(CommandHandler("stack", cmd_stack))
    app.add_handler(CommandHandler("notion", cmd_notion))
