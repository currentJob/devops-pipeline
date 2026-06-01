"""RAG — 웹 검색 기반 최신 데이터 참조 파이프라인.

1순위: Brave Search API (BRAVE_API_KEY 설정 시) → 실시간 웹 결과
2순위: 로컬 문서 (*.md / *.txt / *.rst) → 프로젝트 컨텍스트 보완
"""

from __future__ import annotations

import logging

import aiohttp

from app import config

logger = logging.getLogger(__name__)

MAX_DOCS = 5
MAX_CONTENT_CHARS = 1500
_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


async def _web_search_docs(query: str) -> list[dict]:
    if not config.BRAVE_API_KEY:
        return []
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                _BRAVE_URL,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": config.BRAVE_API_KEY,
                },
                params={"q": query, "count": MAX_DOCS},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp,
        ):
            if resp.status != 200:
                logger.warning("Brave Search 비-200: %s", resp.status)
                return []
            data = await resp.json()
    except aiohttp.ClientError as exc:
        logger.warning("Brave Search 실패: %s", exc)
        return []

    docs = []
    for result in data.get("web", {}).get("results", [])[:MAX_DOCS]:
        docs.append(
            {
                "source": result.get("title", ""),
                "url": result.get("url", ""),
                "content": result.get("description", "")[:MAX_CONTENT_CHARS],
            }
        )
    return docs


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
    """웹 검색 결과 + 로컬 문서를 합쳐 Claude 프롬프트용 컨텍스트 블록 반환."""
    docs: list[dict] = []

    web_docs = await _web_search_docs(query)
    docs.extend(web_docs)

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
