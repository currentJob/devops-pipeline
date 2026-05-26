"""RAG (Retrieval-Augmented Generation) 검색 모듈.

Notion 워크스페이스와 로컬 파일에서 쿼리 관련 문서를 검색하여
Claude 프롬프트에 주입할 컨텍스트를 구성한다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MAX_DOCS = 5
MAX_CONTENT_CHARS = 1500


async def _notion_docs(query: str) -> list[dict]:
    from app import config
    from app.notion import client as notion_client

    if not config.NOTION_TOKEN:
        return []
    try:
        pages = await notion_client.search_pages(config.NOTION_TOKEN, query, page_size=MAX_DOCS)
        docs: list[dict] = []
        for page in pages:
            content = await notion_client.fetch_page_content(
                config.NOTION_TOKEN, page["id"], max_chars=MAX_CONTENT_CHARS
            )
            docs.append({
                "source": f"Notion: {page['title']}",
                "url": page["url"],
                "content": content or page["title"],
            })
        return docs
    except Exception as exc:
        logger.warning("Notion 검색 실패: %s", exc)
        return []


def _file_docs(query: str) -> list[dict]:
    from app.tools.filesystem import WORKSPACE

    keywords = {w.lower() for w in query.split() if len(w) > 1}
    docs: list[dict] = []
    for ext in ("*.md", "*.txt", "*.rst"):
        for path in WORKSPACE.rglob(ext):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(kw in text.lower() for kw in keywords):
                rel = str(path.relative_to(WORKSPACE))
                docs.append({"source": f"파일: {rel}", "content": text[:MAX_CONTENT_CHARS]})
                if len(docs) >= MAX_DOCS:
                    return docs
    return docs


async def retrieve_context(query: str) -> str:
    """쿼리 관련 외부 문서를 검색하고 컨텍스트 블록 문자열 반환. 결과 없으면 빈 문자열."""
    docs: list[dict] = []

    notion_docs = await _notion_docs(query)
    docs.extend(notion_docs)

    if len(docs) < MAX_DOCS:
        file_docs = _file_docs(query)
        docs.extend(file_docs[: MAX_DOCS - len(docs)])

    if not docs:
        return ""

    lines = ["[참고 문서]"]
    for i, doc in enumerate(docs, 1):
        url_line = f"\n출처: {doc['url']}" if doc.get("url") else ""
        lines.append(f"\n--- {i}. {doc['source']}{url_line} ---\n{doc['content']}")
    lines.append("\n[/참고 문서]")
    return "\n".join(lines)
