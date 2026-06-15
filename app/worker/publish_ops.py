"""vault 발행 토글 — 노트 목록/플래그 토글/발행 적용(export+commit+push).

봇 `/notes` 명령의 워커측 백엔드. frontmatter 의 `publish` 필드만 토글하고(=vault 쓰기,
허용 sandbox), "발행 적용" 시 publish:true 노트를 site/content 로 export 한 뒤 그 경로만
커밋·push 한다. 제외 규칙(`digests/`·`_*`)·발행 판정·export 는 scripts/publish_vault.py 를
재사용(단일 진실원)한다.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import re
from pathlib import Path

from app import config
from app.tools import filesystem
from app.worker import git_ops

logger = logging.getLogger(__name__)

# scripts/ 는 패키지가 아니라 단독 스크립트 → 파일 경로로 로드해 재사용.
_PV_PATH = Path(__file__).resolve().parents[2] / "scripts" / "publish_vault.py"
_spec = importlib.util.spec_from_file_location("publish_vault", _PV_PATH)
publish_vault = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(publish_vault)

NOTES_MAX = 50  # 인라인 키보드/메시지 한도 보호 — 초과분은 로컬에서
_APPLY_MSG = "Docs: vault 발행 노트 갱신 (site/content)"
_SITE_CONTENT = "site/content"

_FM_BLOCK = re.compile(r"^(---\n)(.*?)(\n---)", re.DOTALL)
_PUB_LINE = re.compile(r"^publish:.*$", re.IGNORECASE | re.MULTILINE)
_TITLE_RE = re.compile(r'^title:\s*"?(.*?)"?\s*$', re.IGNORECASE | re.MULTILINE)


def _vault() -> Path:
    return filesystem.WORKSPACE / config.VAULT_SUBDIR


def _title(text: str, fallback: str) -> str:
    m = _FM_BLOCK.match(text)
    if m:
        t = _TITLE_RE.search(m.group(2))
        if t and t.group(1).strip():
            return t.group(1).strip()
    return fallback


def list_notes(vault: Path | None = None) -> list[dict]:
    """발행 대상 후보 노트를 (카테고리, 제목) 정렬로 반환.

    각 항목: {path(rel posix), title, category(상위 폴더 posix, 루트는 ''), published}.
    digests/·`_*` 생성물은 제외(숨김).
    """
    vault = vault or _vault()
    rows: list[dict] = []
    if not vault.is_dir():
        return rows
    for p in sorted(vault.rglob("*.md")):
        rel = p.relative_to(vault)
        if publish_vault._excluded(rel):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        category = "" if rel.parent == Path(".") else rel.parent.as_posix()
        rows.append(
            {
                "path": rel.as_posix(),
                "title": _title(text, p.stem),
                "category": category,
                "published": publish_vault.is_published(text),
            }
        )
    rows.sort(key=lambda r: (r["category"], r["title"]))
    return rows


def _safe_note(vault: Path, rel_path: str) -> Path:
    """rel_path 를 vault 내부 .md 노트로 안전 해석. traversal·제외·부재 시 ValueError."""
    if rel_path.startswith("/"):
        raise ValueError("절대경로 거부")
    if ".." in rel_path.replace("\\", "/").split("/"):
        raise ValueError("path traversal 거부")
    root = vault.resolve()
    p = (root / rel_path).resolve()
    if not p.is_relative_to(root):
        raise ValueError("vault 이탈 거부")
    rel = p.relative_to(root)
    if publish_vault._excluded(rel):
        raise ValueError("발행 불가 노트(생성물/digests)")
    if p.suffix != ".md" or not p.is_file():
        raise ValueError(f"노트 없음: {rel_path}")
    return p


def _set_fm_publish(text: str, value: bool) -> str:
    """frontmatter 의 publish 라인을 value 로 설정(없으면 추가). 프론트매터 없으면 새로 생성."""
    flag = "true" if value else "false"
    m = _FM_BLOCK.match(text)
    if not m:
        return f"---\npublish: {flag}\n---\n\n{text}"
    body = m.group(2)
    if _PUB_LINE.search(body):
        body = _PUB_LINE.sub(f"publish: {flag}", body, count=1)
    else:
        body = f"{body}\npublish: {flag}"
    return text[: m.start()] + m.group(1) + body + m.group(3) + text[m.end() :]


def set_publish(rel_path: str, value: bool, vault: Path | None = None) -> dict:
    """노트 frontmatter 의 publish 를 토글하고 갱신 상태를 반환."""
    vault = vault or _vault()
    p = _safe_note(vault, rel_path)
    text = p.read_text(encoding="utf-8", errors="ignore")
    p.write_text(_set_fm_publish(text, value), encoding="utf-8")
    return {"path": rel_path, "published": value}


def _export_site() -> int:
    """publish:true 노트를 site/content 로 export(동기). 발행 개수 반환."""
    out = filesystem.WORKSPACE / "site" / "content"
    return publish_vault.export(_vault(), out)


async def apply() -> dict:
    """발행 적용: export → site/content 경로만 커밋 → push. 변경 없으면 commit/push 생략."""
    count = await asyncio.to_thread(_export_site)
    head = await git_ops.commit_paths([_SITE_CONTENT], _APPLY_MSG)
    if head is None:
        return {"ok": True, "count": count, "detail": "site/content 변경 없음 — 커밋·push 생략"}
    branch = await git_ops.current_branch()
    pushed = await git_ops.push(branch)
    return {"ok": True, "count": count, "detail": f"{head}\n{pushed}"}
