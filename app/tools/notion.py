from __future__ import annotations

import json

from app import config
from app.notion import client as notion_client


async def _notion_search(query: str, limit: int = 10) -> str:
    if not config.NOTION_TOKEN:
        return "거부: NOTION_TOKEN 미설정"
    try:
        pages = await notion_client.search_pages(config.NOTION_TOKEN, query, limit)
    except RuntimeError as e:
        return f"Notion 검색 실패: {e}"
    return json.dumps(pages, ensure_ascii=False)


async def _notion_create_page(title: str, content: str, icon: str | None = None) -> str:
    if not config.NOTION_TOKEN:
        return "거부: NOTION_TOKEN 미설정"
    if not config.NOTION_PARENT_PAGE_ID:
        return "거부: NOTION_PARENT_PAGE_ID 미설정"
    result = await notion_client.create_page(
        config.NOTION_TOKEN,
        config.NOTION_PARENT_PAGE_ID,
        title,
        content,
        icon,
    )
    return json.dumps(result, ensure_ascii=False)
