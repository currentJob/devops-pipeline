"""Notion REST API 의 가벼운 클라이언트 (워커용).

aiohttp 만 의존하며 외부 SDK 없음.
필요한 환경 변수:
- NOTION_TOKEN: Internal Integration Token
- NOTION_PARENT_PAGE_ID: 새 페이지가 생성될 부모 페이지 (통합과 공유되어 있어야 함)
"""

from __future__ import annotations

from typing import Any

import aiohttp

from app.notion.markdown import markdown_to_blocks

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TIMEOUT_S = 15


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _extract_page_meta(page: dict) -> dict:
    """search 결과 항목에서 id, title, url 만 뽑아 가벼운 dict 로."""
    title = "(제목 없음)"
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            title_arr = prop.get("title", [])
            if title_arr:
                title = "".join(t.get("plain_text", "") for t in title_arr)
            break
    return {
        "id": page.get("id"),
        "title": title,
        "url": page.get("url"),
    }


async def check_connection(token: str, parent_page_id: str) -> dict:
    """토큰 유효성 + 부모 페이지 접근 권한을 한 번에 확인.

    반환: {
        "token_ok": bool,
        "page_ok": bool,
        "page_status": int | None,
        "error": str | None,
    }
    """
    result: dict = {"token_ok": False, "page_ok": False, "page_status": None, "error": None}
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_S)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{NOTION_API}/search",
            headers=_headers(token),
            json={"query": "", "page_size": 1},
            timeout=timeout,
        ) as resp:
            if resp.status == 401:
                result["error"] = "NOTION_TOKEN 이 유효하지 않음 (401 Unauthorized)"
                return result
            if resp.status >= 400:
                data = await resp.json()
                result["error"] = f"Notion API 오류 {resp.status}: {data.get('message', data)}"
                return result
            result["token_ok"] = True

        async with session.get(
            f"{NOTION_API}/pages/{parent_page_id}",
            headers=_headers(token),
            timeout=timeout,
        ) as resp:
            result["page_status"] = resp.status
            if resp.status == 200:
                result["page_ok"] = True
            elif resp.status == 404:
                result["error"] = "NOTION_PARENT_PAGE_ID 에 해당하는 페이지를 찾을 수 없음 (404)"
            elif resp.status in (401, 403):
                result["error"] = (
                    "페이지에 Integration 이 연결되지 않음 (403) — "
                    "Notion 페이지 → ··· → Connections 에서 Integration 추가 필요"
                )
            else:
                data = await resp.json()
                result["error"] = f"페이지 조회 실패 {resp.status}: {data.get('message', data)}"

    return result


async def search_pages(token: str, query: str, page_size: int = 10) -> list[dict]:
    """페이지 검색. [{id, title, url}, ...] 반환."""
    async with (
        aiohttp.ClientSession() as session,
        session.post(
            f"{NOTION_API}/search",
            headers=_headers(token),
            json={
                "query": query,
                "page_size": page_size,
                "filter": {"value": "page", "property": "object"},
            },
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_S),
        ) as resp,
    ):
        data = await resp.json()
        if resp.status >= 400:
            raise RuntimeError(f"Notion search 실패 {resp.status}: {data.get('message', data)}")
        results = data.get("results", [])
        return [_extract_page_meta(p) for p in results]


async def fetch_page_content(token: str, page_id: str, max_chars: int = 1500) -> str:
    """페이지 블록에서 순수 텍스트 내용 추출 (RAG 컨텍스트용)."""
    async with (
        aiohttp.ClientSession() as session,
        session.get(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=_headers(token),
            params={"page_size": 50},
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_S),
        ) as resp,
    ):
        if resp.status != 200:
            return ""
        data = await resp.json()

    parts: list[str] = []
    for block in data.get("results", []):
        btype = block.get("type", "")
        bdata = block.get(btype, {})
        rich = bdata.get("rich_text", [])
        text = "".join(r.get("plain_text", "") for r in rich)
        if text:
            parts.append(text)
    return "\n".join(parts)[:max_chars]


async def create_page(
    token: str,
    parent_page_id: str,
    title: str,
    markdown: str,
    icon: str | None = None,
) -> dict:
    """parent_page_id 하위에 페이지 생성. {id, url} 또는 {error} 반환."""
    payload: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
        "children": markdown_to_blocks(markdown),
    }
    if icon:
        payload["icon"] = {"type": "emoji", "emoji": icon}

    async with (
        aiohttp.ClientSession() as session,
        session.post(
            f"{NOTION_API}/pages",
            headers=_headers(token),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_S),
        ) as resp,
    ):
        data = await resp.json()
        if resp.status >= 400:
            msg = data.get("message", str(data))
            if resp.status == 404:
                hint = " — NOTION_PARENT_PAGE_ID 가 유효한 페이지 ID 인지 확인"
            elif resp.status in (401, 403):
                hint = " — Notion 페이지에 해당 Integration 이 연결(Connect)되어 있는지 확인"
            else:
                hint = ""
            return {"error": f"{resp.status}: {msg}{hint}"}
        return {"id": data["id"], "url": data["url"]}
