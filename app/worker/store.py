"""작업 이력 저장소 — SQLAlchemy Core 비동기 엔진 기반.

DB_BACKEND 설정에 따라 백엔드 선택:
  - sqlite   (기본): DATA_DIR/tasks.db, aiosqlite 드라이버. 추가 인프라 불필요.
  - postgres       : POSTGRES_* 설정으로 asyncpg 연결. docker compose --profile postgres.

SQLAlchemy Core 가 두 방언(SQL dialect)의 구문 차이를 흡수하므로 동일 코드로 동작한다.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
from enum import StrEnum
from pathlib import Path

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app import config

logger = logging.getLogger(__name__)


class TaskStatus(StrEnum):
    """작업 수명주기 상태 — DB status 컬럼에 그대로 저장되는 문자열 값."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


_metadata = MetaData()

tasks = Table(
    "tasks",
    _metadata,
    Column("task_id", String, primary_key=True),
    Column("description", Text, nullable=False),
    Column("status", String, nullable=False, server_default=TaskStatus.PENDING.value),
    Column("result", Text),
    Column("summary", Text),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),
    Column("completed_at", String),
)

_engine: AsyncEngine | None = None


def _database_url() -> str:
    """설정 기반 SQLAlchemy 비동기 연결 URL."""
    if config.DB_BACKEND == "postgres":
        return (
            f"postgresql+asyncpg://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}"
            f"@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
        )
    db_path = Path(os.environ.get("DATA_DIR", "data")) / "tasks.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(_database_url(), pool_pre_ping=True)
    return _engine


async def dispose() -> None:
    """엔진 풀 정리 (종료·테스트용)."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


def _ensure_summary_column(sync_conn) -> None:
    """기존 DB 호환: summary 컬럼이 없으면 추가 (sqlite/postgres 공통 구문)."""
    cols = {c["name"] for c in inspect(sync_conn).get_columns("tasks")}
    if "summary" not in cols:
        sync_conn.execute(text("ALTER TABLE tasks ADD COLUMN summary TEXT"))


async def init() -> None:
    # postgres 는 docker 에서 동시 기동되므로 준비될 때까지 재시도 (sqlite 는 1회)
    attempts = 15 if config.DB_BACKEND == "postgres" else 1
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            async with _get_engine().begin() as conn:
                await conn.run_sync(_metadata.create_all)
                await conn.run_sync(_ensure_summary_column)
            return
        except Exception as e:  # noqa: BLE001 — postgres 기동 대기 후 재시도
            last_err = e
            if i < attempts - 1:
                logger.warning("DB 연결 대기 중 (%d/%d): %s", i + 1, attempts, e)
                await asyncio.sleep(2)
    assert last_err is not None
    raise last_err


async def create(task_id: str, description: str) -> None:
    try:
        async with _get_engine().begin() as conn:
            await conn.execute(
                insert(tasks).values(
                    task_id=task_id, description=description[:300], created_at=_now()
                )
            )
    except IntegrityError:
        pass  # 이미 존재 — 무시 (INSERT OR IGNORE 와 동등)


async def set_running(task_id: str) -> None:
    async with _get_engine().begin() as conn:
        await conn.execute(
            update(tasks)
            .where(tasks.c.task_id == task_id)
            .values(status=TaskStatus.RUNNING.value, attempts=tasks.c.attempts + 1)
        )


async def set_done(task_id: str, result: str, *, failed: bool = False) -> None:
    async with _get_engine().begin() as conn:
        await conn.execute(
            update(tasks)
            .where(tasks.c.task_id == task_id)
            .values(
                status=(TaskStatus.FAILED if failed else TaskStatus.DONE).value,
                result=result[:4000],
                completed_at=_now(),
            )
        )


async def set_summary(task_id: str, summary: str) -> None:
    async with _get_engine().begin() as conn:
        await conn.execute(
            update(tasks).where(tasks.c.task_id == task_id).values(summary=summary[:500])
        )


async def get_recent_summaries(limit: int = 3) -> list[dict]:
    """요약본이 있는 최근 작업을 최신순으로 반환 (새 작업 참조용)."""
    if limit <= 0:
        return []
    async with _get_engine().connect() as conn:
        rows = await conn.execute(
            select(tasks.c.summary, tasks.c.created_at)
            .where(tasks.c.summary.isnot(None), tasks.c.summary != "")
            .order_by(tasks.c.created_at.desc())
            .limit(limit)
        )
        return [dict(r._mapping) for r in rows]


async def get_recent(limit: int = 10) -> list[dict]:
    async with _get_engine().connect() as conn:
        rows = await conn.execute(
            select(
                tasks.c.task_id,
                tasks.c.description,
                tasks.c.status,
                tasks.c.result,
                tasks.c.created_at,
                tasks.c.completed_at,
            )
            .order_by(tasks.c.created_at.desc())
            .limit(limit)
        )
        return [dict(r._mapping) for r in rows]


def _now() -> str:
    # 초 단위 포함 — 같은 분에 생성된 작업의 정렬(get_recent/메모리)이 비결정적이지 않도록.
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
