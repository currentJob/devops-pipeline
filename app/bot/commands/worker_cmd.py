from telegram import Update
from telegram.ext import ContextTypes

from app import config
from app.bot.commands import _authorized, _dispatch_to_worker
from app.notion import client as notion_client


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

    await _dispatch_to_worker(update, description, upload_to_notion=True)


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
