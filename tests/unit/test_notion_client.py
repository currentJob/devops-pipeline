"""app/notion_client.py 의 순수 함수(파서) 단위 테스트.

HTTP 호출(search_pages, create_page) 은 통합 테스트로 미루고,
마크다운 → 블록 변환만 검증.
"""

from __future__ import annotations

from app import notion_client


def test_markdown_to_blocks_headings():
    md = "# H1\n## H2\n### H3"
    blocks = notion_client.markdown_to_blocks(md)
    types = [b["type"] for b in blocks]
    assert types == ["heading_1", "heading_2", "heading_3"]


def test_markdown_to_blocks_bullets():
    md = "- 첫째\n- 둘째"
    blocks = notion_client.markdown_to_blocks(md)
    assert all(b["type"] == "bulleted_list_item" for b in blocks)
    assert len(blocks) == 2


def test_markdown_to_blocks_quote_and_paragraph():
    md = "> 인용\n\n단락 텍스트"
    blocks = notion_client.markdown_to_blocks(md)
    types = [b["type"] for b in blocks]
    assert types == ["quote", "paragraph"]


def test_markdown_to_blocks_code_fence():
    md = "```\nprint('x')\n```"
    blocks = notion_client.markdown_to_blocks(md)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "code"
    assert "print('x')" in blocks[0]["code"]["rich_text"][0]["text"]["content"]


def test_markdown_to_blocks_caps_at_100():
    md = "\n".join(["- 항목"] * 150)
    blocks = notion_client.markdown_to_blocks(md)
    assert len(blocks) == 100  # Notion children API 한도


def test_extract_page_meta_simple():
    page = {
        "id": "abc123",
        "url": "https://www.notion.so/abc123",
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"plain_text": "테스트 페이지"}],
            }
        },
    }
    meta = notion_client._extract_page_meta(page)
    assert meta == {
        "id": "abc123",
        "title": "테스트 페이지",
        "url": "https://www.notion.so/abc123",
    }


def test_extract_page_meta_no_title_property():
    page = {"id": "x", "url": "u", "properties": {}}
    meta = notion_client._extract_page_meta(page)
    assert meta["title"] == "(제목 없음)"


def test_rich_text_chunks_long_content():
    long = "x" * 2500
    chunks = notion_client._rich_text(long)
    assert len(chunks) == 2
    assert chunks[0]["text"]["content"] == "x" * 2000
    assert chunks[1]["text"]["content"] == "x" * 500
