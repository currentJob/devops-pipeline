"""vault MOC(Map of Content) + Dashboard 자동 생성.

계층 태그(area/*) 기준으로 노트를 묶어 인덱스 허브(_MOC_*.md)를 만들고,
Dataview 쿼리 + 정적 요약을 담은 _Dashboard.md 를 생성한다.

생성 노트는 '_' 접두사라 vault_index 인덱싱·vault_search 검색에서 제외된다.
직접 편집하지 말 것 — /reindex 마다 덮어쓴다.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from app.rag.vault_index import _parse_tags

_TITLE_RE = re.compile(r'^title:\s*"?(.+?)"?\s*$', re.MULTILINE)
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _title(text: str, stem: str) -> str:
    m = _TITLE_RE.search(text)
    return m.group(1).strip() if m else stem


def _moc_suffix(area_tag: str) -> str:
    """area/vector-db → vector-db (파일명 세그먼트)."""
    suffix = area_tag.split("area/", 1)[-1].replace("/", "-")
    return _UNSAFE.sub("", suffix).strip() or "기타"


def _scan(vault_dir: Path) -> list[tuple[str, str, list[str]]]:
    """(stem, title, tags) 목록 — '_' 접두사 생성 노트는 제외."""
    notes: list[tuple[str, str, list[str]]] = []
    for path in sorted(vault_dir.rglob("*.md")):
        if path.name.startswith("_"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        notes.append((path.stem, _title(text, path.stem), _parse_tags(text)))
    return notes


def _dashboard(notes: list, area_tags: list[str]) -> str:
    types = Counter(t for _, _, tags in notes for t in tags if t.startswith("type/"))
    areas = Counter(t for _, _, tags in notes for t in tags if t.startswith("area/"))
    techs = Counter(t for _, _, tags in notes for t in tags if t.startswith("tech/"))

    def _fmt(counter: Counter) -> str:
        return ", ".join(f"{k}({v})" for k, v in counter.most_common()) or "(없음)"

    moc_links = "\n".join(f"- [[_MOC_{_moc_suffix(a)}]]" for a in area_tags) or "- (없음)"
    return (
        "---\ntitle: Dashboard\ntags:\n  - _generated\n---\n\n"
        "> [!info] 자동 생성 노트 — `/reindex` 마다 갱신됩니다. 직접 편집하지 마세요.\n\n"
        "## 요약\n"
        f"- 총 노트: {len(notes)}개\n"
        f"- 타입: {_fmt(types)}\n"
        f"- 영역: {_fmt(areas)}\n"
        f"- 기술: {_fmt(techs)}\n\n"
        "## 영역별 MOC\n"
        f"{moc_links}\n\n"
        "## 최근 노트\n"
        '```dataview\nTABLE created, tags\nFROM ""\n'
        'WHERE created AND !contains(file.name, "_MOC") AND file.name != "_Dashboard"\n'
        "SORT created DESC\nLIMIT 15\n```\n\n"
        "## 오래된 노트 (90일+)\n"
        '```dataview\nTABLE updated, tags\nFROM ""\n'
        "WHERE updated AND (date(today) - date(updated)) > dur(90 days)\n"
        "SORT updated ASC\n```\n"
    )


def _moc(area_tag: str, items: list[tuple[str, list[str]]]) -> str:
    lines = [
        f"---\ntitle: 'MOC: {area_tag}'\ntags:\n  - _generated\n---\n",
        f"> [!info] `{area_tag}` 노트 모음 — `/reindex` 마다 자동 갱신됩니다.\n",
    ]
    for title, tags in sorted(items):
        extra = ", ".join(t for t in tags if not t.startswith("area/"))
        lines.append(f"- [[{title}]]" + (f" — {extra}" if extra else ""))
    return "\n".join(lines) + "\n"


def build_moc(vault_dir: Path) -> int:
    """vault 의 MOC + Dashboard 노트를 (재)생성. 생성한 파일 수를 반환."""
    if not vault_dir.is_dir():
        return 0
    notes = _scan(vault_dir)
    if not notes:
        return 0

    # area 태그별 노트 그룹화
    by_area: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for _stem, title, tags in notes:
        for tag in tags:
            if tag.startswith("area/"):
                by_area[tag].append((title, tags))

    written = 0
    for area_tag, items in by_area.items():
        path = vault_dir / f"_MOC_{_moc_suffix(area_tag)}.md"
        path.write_text(_moc(area_tag, items), encoding="utf-8")
        written += 1

    (vault_dir / "_Dashboard.md").write_text(_dashboard(notes, sorted(by_area)), encoding="utf-8")
    written += 1
    return written
