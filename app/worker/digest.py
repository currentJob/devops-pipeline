"""정기 다이제스트 — 최근 vault 노트를 요약한 주간 브리핑 노트 생성.

opt-in(config.DIGEST_ENABLED). 워커 background 루프가 주기적으로 호출하거나
봇 /digest 명령이 즉시 호출한다. LLM(runtime.chat)으로 신규 노트를 요약하고,
best-effort 로 last30days 최근 동향을 덧붙인 뒤 vault_save 로 노트를 남긴다.
"""

from __future__ import annotations

import datetime
import logging
import re
from collections import Counter
from pathlib import Path

from app import config
from app.agent import runtime
from app.rag.vault_index import _parse_tags
from app.tools import filesystem, obsidian
from app.tools.research import recent_research

logger = logging.getLogger(__name__)

_CREATED_RE = re.compile(r"^created:\s*(\d{4}-\d{2}-\d{2})", re.MULTILINE)
_TITLE_RE = re.compile(r'^title:\s*"?(.+?)"?\s*$', re.MULTILINE)


def _recent_notes(vault_dir: Path, days: int) -> list[tuple[str, str, list[str]]]:
    """최근 days 일 내 created 된 노트 (title, 본문요약, tags). 생성물(_)·다이제스트 제외."""
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    out: list[tuple[str, str, list[str]]] = []
    for path in sorted(vault_dir.rglob("*.md")):
        if path.name.startswith("_"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        tags = _parse_tags(text)
        if "type/digest" in tags:
            continue  # 과거 다이제스트는 재요약 대상에서 제외
        m = _CREATED_RE.search(text)
        if not m:
            continue
        try:
            if datetime.date.fromisoformat(m.group(1)) < cutoff:
                continue
        except ValueError:
            continue
        tm = _TITLE_RE.search(text)
        title = tm.group(1).strip() if tm else path.stem
        body = text.split("---", 2)[-1].strip().replace("\n", " ")[:500]
        out.append((title, body, tags))
    return out


def _dominant_tech(notes: list[tuple[str, str, list[str]]]) -> str:
    """신규 노트에서 가장 빈번한 tech/ 태그 → 동향 조사 주제 (없으면 빈 문자열)."""
    techs = Counter(t.split("tech/", 1)[-1] for _, _, tags in notes for t in tags if "tech/" in t)
    return techs.most_common(1)[0][0] if techs else ""


async def generate_digest(days: int | None = None) -> str:
    """최근 노트 요약 다이제스트 노트를 생성하고 vault_save 결과(경로 문자열)를 반환."""
    days = days or config.DIGEST_INTERVAL_DAYS
    today = datetime.date.today().strftime("%Y-%m-%d")
    vault_dir = filesystem.WORKSPACE / config.VAULT_SUBDIR
    notes = _recent_notes(vault_dir, days) if vault_dir.is_dir() else []

    if not notes:
        body = f"> [!summary] TL;DR\n> 최근 {days}일간 새로 추가된 노트가 없습니다.\n"
        return obsidian.vault_save(f"주간 브리핑 {today}", body, "digests", "type/digest")

    listing = "\n".join(f"- {t} [{', '.join(tags)}]: {b}" for t, b, tags in notes)

    # best-effort 최근 동향 — 실패/비활성/에러 메시지는 무시(빈 문자열)
    research_block = ""
    topic = _dominant_tech(notes)
    if topic:
        result = await recent_research(f"{topic} 최근 동향")
        if result and not result.startswith(("조사", "최신 조사")):
            research_block = f"\n\n[참고: {topic} 최근 동향 조사]\n{result}"

    summary = await runtime.chat(
        system=(
            "당신은 지식 큐레이터입니다. 최근 추가된 노트 목록을 한국어로 요약해 주간 브리핑을 작성하세요.\n"
            "형식: 맨 위 `> [!summary] TL;DR` 콜아웃(2-3줄), 이어서 `## 주요 내용` 에 노트별 핵심을 불릿으로.\n"
            "참고 동향 조사가 주어지면 `## 최근 동향` 섹션으로 간단히 덧붙이세요. 과장 없이 사실 기반으로."
        ),
        user=f"최근 {days}일 신규 노트 {len(notes)}개:\n{listing}{research_block}",
    )
    return obsidian.vault_save(f"주간 브리핑 {today}", summary.strip(), "digests", "type/digest")
