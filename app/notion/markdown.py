"""마크다운 → Notion 블록 변환 (순수 함수, HTTP 의존 없음)."""

from __future__ import annotations


def _rich_text(content: str) -> list[dict]:
    if len(content) <= 2000:
        return [{"type": "text", "text": {"content": content}}]
    chunks = [content[i : i + 2000] for i in range(0, len(content), 2000)]
    return [{"type": "text", "text": {"content": c}} for c in chunks]


def _block(block_type: str, text: str) -> dict:
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": _rich_text(text)},
    }


def markdown_to_blocks(md: str) -> list[dict]:
    """단순 마크다운 → Notion 블록. # / ## / ### / - / > / ``` / 단락 지원.

    Notion API 한 호출에 최대 100 블록 제한.
    """
    blocks: list[dict] = []
    in_code = False
    code_buf: list[str] = []
    for raw in md.splitlines():
        line = raw.rstrip()

        if line.startswith("```"):
            if in_code:
                blocks.append(
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": _rich_text("\n".join(code_buf)),
                            "language": "plain text",
                        },
                    }
                )
                code_buf = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_buf.append(line)
            continue

        if not line:
            continue
        if line.startswith("### "):
            blocks.append(_block("heading_3", line[4:]))
        elif line.startswith("## "):
            blocks.append(_block("heading_2", line[3:]))
        elif line.startswith("# "):
            blocks.append(_block("heading_1", line[2:]))
        elif line.startswith("- "):
            blocks.append(_block("bulleted_list_item", line[2:]))
        elif line.startswith("> "):
            blocks.append(_block("quote", line[2:]))
        else:
            blocks.append(_block("paragraph", line))
    return blocks[:100]
