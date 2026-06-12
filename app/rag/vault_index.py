"""vault 노트 벡터 인덱스 — Qdrant + fastembed(로컬 ONNX 임베딩).

vault 의 .md 노트를 벡터화해 의미 기반 검색을 제공한다.
Qdrant 미가용·임베딩 실패 시 호출자가 키워드 검색으로 폴백하도록 None/0 을 반환한다.

- index_note  : 단일 노트 upsert (vault_save 가 호출)
- index_all   : vault 전체 재인덱싱 (/reindex 가 호출)
- semantic_search : 의미 기반 검색 (vault_search 가 호출, 실패 시 None)

임베딩 모델은 fastembed(onnxruntime)로 첫 사용 시 1회 다운로드되어 캐시된다.
qdrant-client 의 fastembed 통합(add/query)을 사용하므로 컬렉션은 add 시 자동 생성된다.
"""

from __future__ import annotations

import logging
import time
import uuid

from app import config

logger = logging.getLogger(__name__)

_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")  # 경로 → 안정적 point id
_SNIPPET = 160
_DOWN_TTL_S = 30.0

_client = None  # 지연 초기화된 QdrantClient
_down_until = 0.0  # 이 시각까지는 미가용으로 간주 (반복적 느린 실패 방지)
_last_error: str | None = None  # 마지막 실패 원인 (진단·에러 표시용)


def last_error() -> str | None:
    """가장 최근 인덱스 실패 원인 (없으면 None)."""
    return _last_error


def _point_id(rel_path: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, rel_path))


def _mark_down(err: Exception | None = None) -> None:
    global _down_until, _last_error
    _down_until = time.monotonic() + _DOWN_TTL_S
    if err is not None:
        _last_error = f"{type(err).__name__}: {err}"


def _get_client():
    """QdrantClient 싱글톤. 비활성/다운 윈도우/초기화 실패 시 None."""
    global _client
    if not config.VAULT_INDEX_ENABLED:
        return None
    if time.monotonic() < _down_until:
        return None
    if _client is not None:
        return _client
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=config.QDRANT_URL, timeout=config.QDRANT_TIMEOUT_S)
        # threads 제한: onnxruntime 이 코어 수만큼 스레드를 띄우며 메모리가 급증하는 것을 막음.
        client.set_model(config.EMBED_MODEL, threads=config.EMBED_THREADS)
        _client = client
        return _client
    except Exception as e:
        logger.warning("Qdrant/임베딩 초기화 실패 → 키워드 검색 폴백: %s", e)
        _mark_down(e)
        return None


def index_note(rel_path: str, title: str, text: str) -> bool:
    """단일 노트를 인덱스에 upsert. 성공 True, 미가용/실패 False (호출자는 무시 가능)."""
    client = _get_client()
    if client is None:
        return False
    try:
        client.add(
            collection_name=config.QDRANT_COLLECTION,
            documents=[text],
            metadata=[{"path": rel_path, "title": title}],
            ids=[_point_id(rel_path)],
        )
        return True
    except Exception as e:
        logger.warning("노트 인덱싱 실패 path=%s: %s", rel_path, e)
        _mark_down(e)
        return False


def index_all(vault_dir) -> int | None:
    """vault_dir 하위 모든 .md 를 재인덱싱. 인덱싱 개수, 미가용 시 None."""
    client = _get_client()
    if client is None:
        return None
    documents: list[str] = []
    metadata: list[dict] = []
    ids: list[str] = []
    for path in sorted(vault_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(vault_dir).as_posix()
        documents.append(text)
        metadata.append({"path": rel, "title": path.stem})
        ids.append(_point_id(rel))
    if not documents:
        return 0
    try:
        client.add(
            collection_name=config.QDRANT_COLLECTION,
            documents=documents,
            metadata=metadata,
            ids=ids,
            batch_size=config.EMBED_BATCH_SIZE,  # 피크 메모리 제한
        )
        return len(documents)
    except Exception as e:
        logger.warning("vault 재인덱싱 실패: %s", e)
        _mark_down(e)
        return None


def semantic_search(query: str, limit: int = 10) -> str | None:
    """의미 기반 검색. 매칭 노트의 경로+요약 문자열, 결과 없음/미가용 시 None."""
    client = _get_client()
    if client is None:
        return None
    try:
        results = client.query(
            collection_name=config.QDRANT_COLLECTION,
            query_text=query,
            limit=limit,
        )
    except Exception as e:
        logger.warning("의미 검색 실패 → 키워드 폴백: %s", e)
        _mark_down(e)
        return None

    lines: list[str] = []
    for r in results:
        meta = r.metadata or {}
        path = meta.get("path", "(unknown)")
        doc = (r.document or "").replace("\n", " ").strip()[:_SNIPPET]
        lines.append(f"- {path} (score={r.score:.2f})\n  {doc}")
    if not lines:
        return None
    return "기존 노트(의미 검색):\n" + "\n".join(lines)
