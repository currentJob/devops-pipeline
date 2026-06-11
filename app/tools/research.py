"""최신 자료 조사 — vendored last30days 스킬 CLI 래퍼.

에이전트가 시의성 있는 주제(트렌드·최신 동향·"최근")에 한해 호출한다.
CLI 를 인자 리스트(exec)로 실행하므로 셸 인젝션이 불가하다.
키 없이 Reddit/HN 조회가 되고, 선택 API 키가 env 에 있으면 더 많은 소스가 활성화된다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from app import config

logger = logging.getLogger(__name__)

# vendor/last30days/last30days.py — 리포 루트 기준 (image: /app, 로컬: 리포 루트)
_DEFAULT_SCRIPT = Path(__file__).resolve().parents[2] / "vendor" / "last30days" / "last30days.py"

_TOPIC_MAX_CHARS = 300
_RESULT_MAX_CHARS = 4000


def _script_path() -> Path:
    return Path(config.RESEARCH_SCRIPT) if config.RESEARCH_SCRIPT else _DEFAULT_SCRIPT


async def recent_research(topic: str) -> str:
    """주제에 대한 최근 N일 소셜/웹 조사 결과를 컨텍스트 블록으로 반환."""
    if not config.RESEARCH_ENABLED:
        return "최신 조사 비활성화됨 (RESEARCH_ENABLED=false)"

    topic = topic.strip()
    if not topic:
        return "조사 거부: 주제가 비어 있음"
    if len(topic) > _TOPIC_MAX_CHARS:
        return f"조사 거부: 주제가 너무 김 (한도 {_TOPIC_MAX_CHARS}자)"

    script = _script_path()
    if not script.is_file():
        logger.warning("last30days 스크립트 없음: %s", script)
        return f"조사 도구 미설치: {script} 없음"

    args = [
        sys.executable,
        str(script),
        topic,
        "--emit",
        "context",
        "--quick",
        "--search",
        config.RESEARCH_SOURCES,
        "--days",
        str(config.RESEARCH_DAYS),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(script.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=config.RESEARCH_TIMEOUT_S
        )
    except TimeoutError:
        return f"조사 타임아웃 {config.RESEARCH_TIMEOUT_S:.0f}s"
    except OSError as e:
        logger.warning("last30days 실행 실패: %s", e)
        return f"조사 실행 실패: {e}"

    out = stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 and not out:
        err = stderr.decode("utf-8", errors="replace").strip()[-500:]
        logger.warning("last30days 비정상 종료 code=%s", proc.returncode)
        return f"조사 실패 (exit={proc.returncode})\n{err}"
    if not out:
        return "조사 결과 없음"

    if len(out) > _RESULT_MAX_CHARS:
        out = out[:_RESULT_MAX_CHARS] + f"\n...(잘림: 총 {len(out)}자)"
    return out
