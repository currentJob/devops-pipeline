"""Obsidian vault 지식 관리 — 마크다운 노트 저장/검색.

Obsidian 은 API 가 없고 vault 폴더의 .md 파일이 곧 데이터다.
워커가 WORKSPACE/<VAULT_SUBDIR> 에 노트를 쓰고, 사용자는 그 폴더를 Obsidian 으로 열어 관리한다.

- YAML 프론트매터(title/aliases/created/updated/tags/source) + 카테고리 폴더 분류
  tags 는 계층형 중첩(type/area/tech), 본문은 콜아웃·위키링크·체크박스 등 Obsidian 기능 활용
- vault_search 로 기존 노트를 확인해 중복 회피 (Notion search 역할 대체)
"""

from __future__ import annotations

import re

from app import clock, config
from app.tools import filesystem  # 지연 참조: 테스트의 WORKSPACE monkeypatch 반영

# 파일/폴더명 금지 문자 (Windows/POSIX 공통 + 제어문자)
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_NAME_MAX = 120
_SEARCH_SNIPPET = 160


def _vault_dir():
    return filesystem.WORKSPACE / config.VAULT_SUBDIR


def _sanitize_segment(name: str) -> str:
    """제목/카테고리를 안전한 단일 경로 세그먼트로. 구분자·.. 제거되어 traversal 불가."""
    name = _UNSAFE.sub("", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name[:_NAME_MAX]


def _split_tags(tags: str) -> list[str]:
    return [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]


def _yaml_list(items: list[str]) -> str:
    """YAML 리스트 렌더 — 비면 ` []`, 아니면 블록 형식.

    블록 형식은 계층형 중첩 태그(type/area/tech)와 Obsidian 프로퍼티 UI 에 친화적이다.
    """
    if not items:
        return " []"
    return "\n" + "\n".join(f"  - {i}" for i in items)


def _frontmatter(title: str, tags: list[str], aliases: list[str]) -> str:
    """Obsidian 프로퍼티 프론트매터 — title/aliases/created/updated/tags/source.

    tags 는 계층형 중첩(예: type/research, area/vector-db, tech/qdrant)을 권장한다.
    """
    today = clock.today().strftime("%Y-%m-%d")
    safe_title = title.replace('"', "'")
    return (
        "---\n"
        f'title: "{safe_title}"\n'
        f"aliases:{_yaml_list(aliases)}\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"tags:{_yaml_list(tags)}\n"
        "source: devops-pipeline\n"
        "---\n\n"
    )


def vault_save(
    title: str, content: str, category: str = "", tags: str = "", aliases: str = ""
) -> str:
    """vault 에 프론트매터 포함 .md 노트를 저장. 동일 파일명 존재 시 -2, -3 … 접미사."""
    base = _sanitize_segment(title)
    if not base:
        return "저장 거부: 제목이 비어 있거나 안전한 파일명으로 변환 불가"

    tag_list = _split_tags(tags)
    alias_list = _split_tags(aliases)
    document = _frontmatter(title, tag_list, alias_list) + content.strip() + "\n"
    if len(document.encode("utf-8")) > filesystem.MAX_FILE_BYTES:
        return f"저장 거부: 콘텐츠가 너무 큼 (한도 {filesystem.MAX_FILE_BYTES} bytes)"

    folder = _vault_dir()
    cat = _sanitize_segment(category)
    if cat:
        folder = folder / cat
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / f"{base}.md"
    n = 2
    while path.exists():
        path = folder / f"{base}-{n}.md"
        n += 1

    path.write_text(document, encoding="utf-8")
    rel = path.relative_to(filesystem.WORKSPACE)

    # 벡터 인덱스에 best-effort 반영 (미가용 시 무시 — 키워드 검색은 계속 동작)
    from app.rag import vault_index

    vault_index.index_note(path.relative_to(_vault_dir()).as_posix(), title, document)

    return f"저장 완료: {rel.as_posix()}"


def vault_search(query: str, limit: int = 10, tags: str = "") -> str:
    """vault 노트 검색. 벡터 의미 검색 우선, 미가용/무결과 시 키워드 검색 폴백.

    tags(쉼표 구분) 지정 시 해당 계층 태그(예: area/devops)를 가진 노트로 한정.
    """
    from app.rag import vault_index

    tag_list = _split_tags(tags)
    semantic = vault_index.semantic_search(query, limit, tag_list or None)
    if semantic:
        return semantic
    return _keyword_search(query, limit)


def _keyword_search(query: str, limit: int = 10) -> str:
    """vault 의 기존 노트를 키워드로 검색 (파일명+본문). 의미 검색 폴백용."""
    vault = _vault_dir()
    if not vault.is_dir():
        return "기존 노트 없음 (vault 비어 있음)"

    keywords = {w.lower() for w in query.split() if len(w) > 1}
    hits: list[str] = []
    for path in sorted(vault.rglob("*.md")):
        if path.name.startswith("_"):
            continue  # 생성된 MOC/Dashboard 노트는 검색 제외
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        haystack = (path.stem + "\n" + text).lower()
        if keywords and not any(kw in haystack for kw in keywords):
            continue
        rel = path.relative_to(vault).as_posix()
        snippet = re.sub(r"\s+", " ", text).strip()[:_SEARCH_SNIPPET]
        hits.append(f"- {rel}\n  {snippet}")
        if len(hits) >= limit:
            break

    if not hits:
        return "매칭되는 기존 노트 없음"
    return "기존 노트:\n" + "\n".join(hits)
