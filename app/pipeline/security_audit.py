"""의존성 보안 감사 — 설치 패키지 인벤토리 + OSV 취약점 조회.

/run 파이프라인의 수집/실행 단계에서 사용한다.
새 의존성 없이 stdlib(importlib.metadata) + 기존 aiohttp 로만 구현.

OSV.dev 공개 API (키 불필요):
- POST /v1/querybatch : 패키지 배치 취약점 조회 (ID 목록)
- GET  /v1/vulns/{id}: 취약점 상세 (요약·심각도·수정 버전)
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
from importlib import metadata
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

OSV_API = "https://api.osv.dev"
_TIMEOUT = aiohttp.ClientTimeout(total=30)
_DETAIL_LIMIT = 40  # 상세 조회할 최대 취약점 수 (API 과부하 방지)
_DETAIL_CONCURRENCY = 8

# 리포트 저장 경로. 컨테이너 WORKDIR=/app 이라 상대 'logs' → /app/logs (볼륨 마운트).
REPORT_DIR = Path(os.environ.get("REPORT_DIR", "logs"))


def list_installed_packages() -> list[dict]:
    """현재 파이썬 환경의 설치 패키지 [{name, version}] (이름 소문자 정규화)."""
    pkgs: dict[str, str] = {}
    for dist in metadata.distributions():
        try:
            name = dist.metadata["Name"]
            version = dist.version
        except Exception:  # 메타데이터 손상 배포본은 건너뜀
            continue
        if name and version:
            pkgs[name.lower()] = version
    return [{"name": n, "version": v} for n, v in sorted(pkgs.items())]


def _summarize_vuln(data: dict) -> dict:
    """OSV 취약점 상세 → {id, summary, severity, fixed} 요약."""
    severity = ""
    for s in data.get("severity", []):
        severity = s.get("score", "") or severity

    fixed: list[str] = []
    for aff in data.get("affected", []):
        for rng in aff.get("ranges", []):
            for ev in rng.get("events", []):
                if "fixed" in ev:
                    fixed.append(ev["fixed"])

    return {
        "id": data.get("id", ""),
        "summary": (data.get("summary") or data.get("details") or "").strip()[:300],
        "severity": severity,
        "fixed": sorted(set(fixed)),
    }


async def _query_batch(session: aiohttp.ClientSession, packages: list[dict]) -> list[list[str]]:
    """OSV querybatch → 패키지별 취약점 ID 리스트 (입력 순서 정렬)."""
    queries = [
        {"version": p["version"], "package": {"name": p["name"], "ecosystem": "PyPI"}}
        for p in packages
    ]
    async with session.post(
        f"{OSV_API}/v1/querybatch", json={"queries": queries}, timeout=_TIMEOUT
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
    return [[v["id"] for v in (r.get("vulns") or [])] for r in data.get("results", [])]


async def _fetch_vuln(session: aiohttp.ClientSession, vuln_id: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        try:
            async with session.get(f"{OSV_API}/v1/vulns/{vuln_id}", timeout=_TIMEOUT) as resp:
                if resp.status != 200:
                    return {
                        "id": vuln_id,
                        "summary": "(상세 조회 실패)",
                        "severity": "",
                        "fixed": [],
                    }
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            return {"id": vuln_id, "summary": "(상세 조회 실패)", "severity": "", "fixed": []}
    return _summarize_vuln(data)


async def scan(packages: list[dict]) -> dict:
    """패키지 목록을 OSV 로 스캔 → 감사 결과 dict.

    반환: {scanned, vulnerable_count, vulnerable[{name,version,vuln_ids}],
           vuln_details{id: 요약}, truncated}
    """
    async with aiohttp.ClientSession() as session:
        batches = await _query_batch(session, packages)

        vulnerable: list[dict] = []
        all_ids: list[str] = []
        for pkg, ids in zip(packages, batches, strict=False):
            if ids:
                vulnerable.append({**pkg, "vuln_ids": ids})
                all_ids.extend(ids)

        unique_ids = list(dict.fromkeys(all_ids))
        detail_ids = unique_ids[:_DETAIL_LIMIT]
        sem = asyncio.Semaphore(_DETAIL_CONCURRENCY)
        details_list = await asyncio.gather(*(_fetch_vuln(session, vid, sem) for vid in detail_ids))

    return {
        "scanned": len(packages),
        "vulnerable_count": len(vulnerable),
        "vulnerable": vulnerable,
        "vuln_details": {d["id"]: d for d in details_list},
        "truncated": len(unique_ids) > len(detail_ids),
    }


def build_findings_text(audit: dict, max_pkgs: int = 30) -> str:
    """Claude 분석/리포트에 넣을 취약점 요약 텍스트."""
    lines = [
        f"스캔한 패키지 수: {audit['scanned']}",
        f"취약 패키지 수: {audit['vulnerable_count']}",
        "",
    ]
    for pkg in audit["vulnerable"][:max_pkgs]:
        lines.append(f"- {pkg['name']} {pkg['version']}")
        for vid in pkg["vuln_ids"]:
            d = audit["vuln_details"].get(vid)
            if d:
                sev = f" [CVSS {d['severity']}]" if d["severity"] else ""
                fix = f" → 수정본: {', '.join(d['fixed'])}" if d["fixed"] else ""
                lines.append(f"    - {vid}{sev}: {d['summary']}{fix}")
            else:
                lines.append(f"    - {vid}")
    if audit["vulnerable_count"] > max_pkgs:
        lines.append(f"... 외 {audit['vulnerable_count'] - max_pkgs}개 패키지")
    return "\n".join(lines)


def build_report_markdown(audit: dict, analysis_summary: str) -> str:
    """저장/Notion 업로드용 교정 리포트 마크다운."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    return "\n".join(
        [
            f"# 의존성 보안 감사 리포트 — {today}",
            "",
            f"- 스캔 패키지: {audit['scanned']}개",
            f"- 취약 패키지: {audit['vulnerable_count']}개",
            "",
            "## AI 분석 및 권장 조치",
            "",
            analysis_summary,
            "",
            "## 원본 취약점 내역",
            "",
            build_findings_text(audit, max_pkgs=100),
        ]
    )


def save_report(markdown: str) -> str:
    """리포트를 REPORT_DIR 에 저장하고 경로 문자열 반환."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORT_DIR / f"security-audit-{ts}.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)
