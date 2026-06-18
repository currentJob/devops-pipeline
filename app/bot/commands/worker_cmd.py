import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

from app import clock, config
from app.bot.commands import _authorized, _dispatch_to_worker, _worker_post_json


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

    await _dispatch_to_worker(update, description, save_to_vault=True)


async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/code <설명>` — 코드 품질 분석 전문 워커."""
    if not _authorized(update):
        return
    description = " ".join(context.args).strip()
    if not description:
        await update.message.reply_text(
            "사용법: `/code <분석 요청>`\n예: `/code app/worker/server.py 보안 취약점 점검`",
            parse_mode="Markdown",
        )
        return
    await _dispatch_to_worker(update, f"[CODE_TASK] {description}")


async def cmd_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/doc <설명>` — 기술 문서 작성 전문 워커."""
    if not _authorized(update):
        return
    description = " ".join(context.args).strip()
    if not description:
        await update.message.reply_text(
            "사용법: `/doc <문서화 요청>`\n예: `/doc worker/server.py README 작성`",
            parse_mode="Markdown",
        )
        return
    await _dispatch_to_worker(update, f"[DOC_TASK] {description}", save_to_vault=True)


async def cmd_infra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/infra <설명>` — 인프라/DevOps 전문 워커."""
    if not _authorized(update):
        return
    description = " ".join(context.args).strip()
    if not description:
        await update.message.reply_text(
            "사용법: `/infra <분석 요청>`\n예: `/infra docker-compose.yml 보안 설정 점검`",
            parse_mode="Markdown",
        )
        return
    await _dispatch_to_worker(update, f"[INFRA_TASK] {description}")


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/plan <설명>` — 복합 작업 분해 후 순차 실행 (Planner Agent)."""
    if not _authorized(update):
        return
    description = " ".join(context.args).strip()
    if not description:
        await update.message.reply_text(
            "사용법: `/plan <복합 작업 설명>`\n예: `/plan 코드 리뷰 후 개선 사항 문서화하고 Obsidian에 저장`",
            parse_mode="Markdown",
        )
        return
    await _dispatch_to_worker(update, f"[PLAN_TASK] {description}", save_to_vault=True)


async def cmd_reindex(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/reindex` — vault 노트를 벡터 인덱스에 재인덱싱."""
    if not _authorized(update):
        return
    await update.message.reply_text("🔄 vault 벡터 재인덱싱 중...")
    data = await _worker_post_json(update, config.WORKER_VAULT_REINDEX_URL, timeout=180)
    if data is None:
        return

    if data.get("ok"):
        moc = data.get("moc")
        moc_txt = f", MOC/Dashboard {moc}개 갱신" if moc else ""
        await update.message.reply_text(f"✅ 재인덱싱 완료 — {data['indexed']}개 노트{moc_txt}")
    else:
        await update.message.reply_text(f"⚠️ 재인덱싱 실패: {data.get('detail', '알 수 없음')}")


async def cmd_digest(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/digest` — 최근 vault 노트를 요약한 주간 브리핑 노트를 즉시 생성."""
    if not _authorized(update):
        return
    await update.message.reply_text("🗞️ 주간 브리핑 생성 중...")
    data = await _worker_post_json(update, config.WORKER_DIGEST_URL, timeout=180)
    if data is None:
        return

    detail = data.get("detail", "알 수 없음")
    if data.get("ok"):
        await update.message.reply_text(f"✅ {detail}")
    else:
        await update.message.reply_text(f"⚠️ 브리핑 생성 실패: {detail}")


async def cmd_history(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/history` — 최근 작업 이력 조회."""
    if not _authorized(update):
        return

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                config.WORKER_TASKS_URL,
                params={"limit": "5"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp,
        ):
            if resp.status != 200:
                await update.message.reply_text(f"⚠️ 이력 조회 실패 (HTTP {resp.status})")
                return
            tasks = await resp.json()
    except aiohttp.ClientError as e:
        await update.message.reply_text(f"🔴 워커 연결 실패: {e}")
        return

    if not tasks:
        await update.message.reply_text("📋 작업 이력 없음")
        return

    _STATUS_ICON = {"done": "✅", "failed": "🔴", "running": "⚙️", "pending": "⏳"}
    lines = ["📋 *최근 작업 이력*\n"]
    for t in tasks:
        icon = _STATUS_ICON.get(t["status"], "❓")
        ts = (t.get("completed_at") or t.get("created_at") or "")[:16]
        desc = t["description"][:55].replace("_", "\\_").replace("[", "\\[")
        lines.append(f"{icon} `{t['task_id']}` _{ts}_\n  {desc}")

    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_ci(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/ci` — 로컬 CI 통합 점검: ruff(린트) + pytest(테스트) + pip-audit(취약점)."""
    if not _authorized(update):
        return
    await _dispatch_to_worker(
        update,
        "bash 도구로 로컬 CI 점검을 순서대로 실행하고 결과를 하나의 한국어 리포트로 합쳐줘:\n"
        "1) 'ruff check .' — 린트\n"
        "2) 'pytest tests/ -q' — 테스트\n"
        "3) 'pip-audit' — 의존성 취약점(CVE)\n\n"
        "맨 위에 전체 `PASS`/`FAIL` 한 줄 헤더를 두고, 각 항목을 ✅/🔴 로 요약해줘 "
        "(린트 오류 수·테스트 통과/실패 수·CVE 수). 실패가 있으면 핵심 사유만 한 줄씩 덧붙여.",
    )


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


def _stack_prompt() -> str:
    """/stack 워커 지시문 — 절차가 길어 핸들러에서 분리."""
    today = clock.today().strftime("%Y-%m-%d")
    year = clock.today().year
    return (
        f"[STACK_TASK] 오늘 날짜: {today}. 다음 절차를 정확히 따라 실행해라.\n\n"
        "1. vault_search 도구로 다음 4가지 쿼리를 차례로 호출해 기존 노트 제목을 수집:\n"
        "   - 'IT 트렌드'\n"
        "   - 'tech stack'\n"
        "   - '학습 로드맵'\n"
        "   - 'technology'\n"
        "2. recent_research 도구로 최근 한 달간 실제 커뮤니티 반응·채택 신호를 수집.\n"
        "3. 검색 결과의 제목들에서 이미 다뤄진 카테고리를 추정 (예: AI 에이전트, "
        "WebAssembly, Iceberg, DevOps, 보안 등). 정확히 매칭되는 카테고리만 '다뤄짐' 으로 분류.\n"
        f"4. {today} 기준으로 다뤄지지 않았거나 보강할 만한 **신규 카테고리 3~5개** 를 선정.\n"
        f"   반드시 {today} 시점에 실제로 주목받고 있는 기술을 선정할 것 (recent_research 근거 활용).\n"
        "   예시 후보군 (시점 맞지 않으면 다른 트렌드로 대체 가능):\n"
        "   - Mojo/Zig (신흥 시스템 언어)\n"
        "   - Tauri/Wails (네이티브 데스크톱)\n"
        "   - Local-First 데이터 (CRDT, Automerge, Yjs)\n"
        "   - Edge AI/추론 (Cloudflare Workers AI, Vercel AI SDK)\n"
        "   - DuckDB·OLAP 임베디드\n"
        "   - HTMX/Hyperscript (HTML-driven 프론트)\n"
        "   - Bazel/Nx (모노레포 빌드)\n"
        "   - WebGPU\n"
        "   - 실시간 협업 (Liveblocks, PartyKit)\n"
        "   * 위는 예시일 뿐 — 기존과 겹치지 않으면 OK.\n"
        f"5. {today} 기준 각 카테고리에 대해 마크다운 섹션을 작성:\n"
        "   - ## 카테고리명\n"
        f"   - ### {today} 기준 트렌드 개요 (2~4문장, 현재 시점 채택률·성숙도 포함)\n"
        "   - ### 핵심 기술 스택 (불릿)\n"
        "   - ### 추천 학습 자료 (가능하면 알고 있는 공식 문서/주요 블로그 링크)\n"
        "   - ### 적합한 역할\n"
        f"6. 본문 맨 앞에 '{today} 기준 신규 트렌드를 선정한 이유' 서론 + 맨 뒤에 '우선순위 추천' 짧게.\n"
        "7. vault_save 호출:\n"
        f"   - title: '{year} 신규 트렌드 — {today}'\n"
        "   - content: 위 마크다운\n"
        "   - category: 'IT 트렌드'\n"
        "   - tags: '트렌드,기술스택'\n"
        "8. 응답: 저장된 노트 경로만 한 줄로 알려줘. 추가 설명 불필요."
    )


async def cmd_stack(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/stack` — IT 트렌드를 조사해서 Obsidian vault 에 새 노트 생성. 중복 회피."""
    if not _authorized(update):
        return
    await _dispatch_to_worker(update, _stack_prompt())


def _poc_prompt(theme: str) -> str:
    """/poc 워커 지시문 — 호환 서비스 조합 → prompts/output/poc/ 에 PoC 스캐폴드."""
    today = clock.today().strftime("%Y-%m-%d")
    theme_line = (
        f"테마: {theme}" if theme else "테마 미지정 — recent_research 로 조합 주제를 직접 선정"
    )
    return (
        f"[POC_TASK] 오늘 날짜: {today}. {theme_line}.\n\n"
        "서로 호환되는 최신 서비스/도구를 조합해 데이터가 흐르는(A→B→출력) 작은 "
        "end-to-end PoC 프로젝트 스캐폴드를 prompts/output/poc/<slug>/ 에 생성하라.\n"
        "- 조합 전 recent_research 로 호환성·채택 신호를 확인하고 README 에 근거를 남길 것.\n"
        "- 파일 7개 이내 최소 스캐폴드: README.md, docker-compose.yml, 서비스별 최소코드+Dockerfile, HANDOFF.md.\n"
        "- 실제 빌드 가능한 형태로 작성(의사코드 금지). 실행·검증은 하지 마라(권한 밖).\n"
        "- 마지막 응답은 생성 경로 + '로컬 Claude Code 로 빌드·검증하세요' 한 줄."
    )


async def cmd_poc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/poc [테마]` — 호환 서비스를 조합한 end-to-end PoC 스캐폴드 생성(무실행)."""
    if not _authorized(update):
        return
    theme = " ".join(context.args).strip()
    await _dispatch_to_worker(update, _poc_prompt(theme))
