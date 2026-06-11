"""워커 기동 자가점검 — 런타임 의존성 상태를 비차단으로 확인.

단위 테스트(mock)가 못 잡는 배포·통합 결함(컨테이너 권한, Qdrant 연결, 임베딩 모델
캐시, git dubious ownership 등)을 기동 직후·요청 전에 드러낸다.

각 점검은 예외를 삼키고 {name, ok, detail} 를 돌려준다(비차단 — 실패해도 워커는 뜬다).
server.main() 이 기동 시 로그로 남기고, GET /selfcheck 가 JSON 으로 노출한다.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import aiohttp

from app import config


def _result(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


async def _check_db() -> dict:
    try:
        from app.worker import store

        await store.get_recent(1)
        return _result("db", True, f"{config.DB_BACKEND} 연결 OK")
    except Exception as e:  # noqa: BLE001 — 진단용, 모든 실패를 detail 로
        return _result("db", False, f"{type(e).__name__}: {e}")


async def _check_workspace_git() -> dict:
    from app.tools.filesystem import WORKSPACE

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(WORKSPACE),
            "rev-parse",
            "--is-inside-work-tree",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        text = out.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0 and "true" in text:
            return _result("workspace_git", True, "git 접근 OK")
        if "dubious ownership" in text:
            return _result("workspace_git", False, "dubious ownership — safe.directory 필요")
        return _result("workspace_git", False, text[:120] or "git repo 아님")
    except FileNotFoundError:
        return _result("workspace_git", False, "git 미설치")
    except Exception as e:  # noqa: BLE001
        return _result("workspace_git", False, f"{type(e).__name__}: {e}")


def _check_vault() -> dict:
    from app.tools.filesystem import WORKSPACE

    vault = WORKSPACE / config.VAULT_SUBDIR
    if not vault.is_dir():
        return _result("vault", True, "폴더 없음 (런타임 생성 예정)")
    count = sum(1 for _ in vault.rglob("*.md"))
    return _result("vault", True, f"노트 {count}개")


async def _check_qdrant() -> dict:
    if not config.VAULT_INDEX_ENABLED:
        return _result("qdrant", True, "비활성 (VAULT_INDEX_ENABLED=false)")
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                f"{config.QDRANT_URL}/readyz",
                timeout=aiohttp.ClientTimeout(total=config.QDRANT_TIMEOUT_S),
            ) as resp,
        ):
            if resp.status == 200:
                return _result("qdrant", True, f"{config.QDRANT_URL} 연결 OK")
            return _result("qdrant", False, f"{config.QDRANT_URL} HTTP {resp.status}")
    except Exception as e:  # noqa: BLE001
        return _result("qdrant", False, f"연결 실패: {type(e).__name__}")


def _check_embedding_cache() -> dict:
    if not config.VAULT_INDEX_ENABLED:
        return _result("embedding", True, "비활성")
    cache = os.environ.get("FASTEMBED_CACHE_PATH")
    model = config.EMBED_MODEL.split("/")[-1]
    if not cache:
        return _result("embedding", True, f"{model} (캐시 경로 미설정 — 기본 위치 사용)")
    cache_dir = Path(cache)
    if not cache_dir.exists():
        return _result("embedding", True, f"{model} 미다운로드 (첫 사용 시 다운로드)")
    onnx = list(cache_dir.rglob("*.onnx"))
    if onnx:
        return _result("embedding", True, f"{model} 캐시됨")
    # 디렉터리는 있으나 모델 파일 없음 = 손상/불완전 (NO_SUCHFILE 원인)
    return _result("embedding", False, f"{model} 캐시 불완전 — {cache} 삭제 후 재다운로드 필요")


def _check_llm() -> dict:
    if config.CLAUDE_API_KEY:
        return _result("llm", True, "Claude API 키 설정됨")
    if config.VLLM_ENDPOINT:
        return _result("llm", True, f"vLLM 설정됨 ({config.VLLM_ENDPOINT})")
    return _result("llm", False, "백엔드 미설정 (CLAUDE_API_KEY 또는 VLLM_ENDPOINT 필요)")


async def run_checks() -> list[dict]:
    """모든 자가점검 실행. 각 항목 {name, ok, detail}. 예외는 항목 내부에서 흡수."""
    db, git, qdrant = await asyncio.gather(_check_db(), _check_workspace_git(), _check_qdrant())
    return [db, git, _check_vault(), qdrant, _check_embedding_cache(), _check_llm()]
