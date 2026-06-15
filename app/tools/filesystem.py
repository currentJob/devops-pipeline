from __future__ import annotations

from pathlib import Path

WORKSPACE = Path("/workspace")
WRITE_PREFIX = "prompts/output/"
MAX_FILE_BYTES = 1_000_000  # 1 MB


def _safe_path(rel: str) -> Path:
    if rel.startswith("/"):
        raise ValueError(f"absolute path 거부: {rel}")
    if ".." in rel.replace("\\", "/").split("/"):
        raise ValueError(f"path traversal 거부: {rel}")
    # 심볼릭 링크까지 해소한 뒤 경로 포함 관계로 검사 (prefix 문자열 비교의 오탐 회피)
    root = WORKSPACE.resolve()
    p = (root / rel).resolve()
    if not p.is_relative_to(root):
        raise ValueError(f"workspace 이탈: {rel}")
    return p


def read_file(path: str) -> str:
    try:
        p = _safe_path(path)
    except ValueError as e:
        return f"거부: {e}"
    if not p.is_file():
        return f"파일 없음: {path}"
    size = p.stat().st_size
    if size > MAX_FILE_BYTES:
        return f"파일 너무 큼: {size} bytes (한도 {MAX_FILE_BYTES})"
    return p.read_text(encoding="utf-8", errors="replace")


def write_file(path: str, content: str) -> str:
    if not path.startswith(WRITE_PREFIX):
        return f"쓰기 거부: '{WRITE_PREFIX}' 로 시작해야 함 (받은: {path!r})"
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        return f"콘텐츠 너무 큼: 한도 {MAX_FILE_BYTES} bytes"
    try:
        p = _safe_path(path)
    except ValueError as e:
        return f"거부: {e}"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"저장 완료: {path} ({len(content)} chars)"
