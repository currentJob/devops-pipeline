"""vault → site/content 발행 export.

frontmatter 에 `publish: true` 인 노트만 git 추적 디렉토리(site/content/)로 복사한다.
vault/ 자체는 .gitignore 로 비공개(.env 취급)이므로, 미발행 노트는 절대 git 에 올라가지 않는다.

흐름: vault 에서 노트 작성 → frontmatter 에 publish: true → 이 스크립트 실행
      → site/content 갱신 → 커밋·푸시 → .github/workflows/blog.yml 이 Quartz 로 빌드·배포.

제외: `_` 로 시작하는 생성물(MOC/Dashboard), `digests/` 폴더.
카테고리: vault 의 폴더 구조를 그대로 보존(= Quartz 의 폴더 페이지/Explorer).
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "vault"
OUT = ROOT / "site" / "content"

_FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_PUBLISH_RE = re.compile(r"^publish:\s*true\s*$", re.IGNORECASE | re.MULTILINE)

_DEFAULT_INDEX = """---
title: "DevOps Vault — 기술 노트"
publish: true
---

> [!summary] 이 사이트
> devops-pipeline 봇이 정리한 기술 노트를 카테고리별로 공개합니다.

왼쪽 Explorer 에서 카테고리(폴더)별로, 태그로도 노트를 탐색할 수 있습니다.
"""


def is_published(text: str) -> bool:
    """frontmatter 에 publish: true 가 있으면 True."""
    m = _FM_RE.match(text)
    return bool(m and _PUBLISH_RE.search(m.group(1)))


def _excluded(rel: Path) -> bool:
    """digests/ 또는 `_` 로 시작하는 경로 세그먼트는 제외."""
    return rel.parts[0] == "digests" or any(part.startswith("_") for part in rel.parts)


def collect(vault: Path) -> list[Path]:
    """publish: true 인 노트 경로 목록(제외 규칙 적용)."""
    out: list[Path] = []
    for p in sorted(vault.rglob("*.md")):
        if _excluded(p.relative_to(vault)):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if is_published(text):
            out.append(p)
    return out


def export(vault: Path, out: Path) -> int:
    """발행 노트를 폴더 구조 보존해 out 으로 복사(깨끗이 재생성). 발행 개수 반환."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / ".gitkeep").write_text("", encoding="utf-8")

    notes = collect(vault)
    for p in notes:
        dest = out / p.relative_to(vault)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)

    # 홈페이지 보장 — 발행 노트에 index.md 가 없으면 기본 랜딩 생성
    if not (out / "index.md").exists():
        (out / "index.md").write_text(_DEFAULT_INDEX, encoding="utf-8")

    return len(notes)


def main() -> int:
    if not VAULT.is_dir():
        print(f"vault 없음: {VAULT}", file=sys.stderr)
        return 1
    n = export(VAULT, OUT)
    print(f"발행 노트 {n}개 → {OUT.relative_to(ROOT).as_posix()}/")
    if n == 0:
        print("게시할 노트가 없습니다 — vault 노트 frontmatter 에 'publish: true' 를 추가하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
