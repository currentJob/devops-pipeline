"""작업 이력 저장소 — SQLite 기반, 추가 인프라 불필요.

DATA_DIR 환경변수로 경로 지정 (기본: ./data). Docker 에서는 볼륨 마운트 권장.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

_DB_PATH = Path(os.environ.get("DATA_DIR", "data")) / "tasks.db"


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id      TEXT PRIMARY KEY,
                description  TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'pending',
                result       TEXT,
                attempts     INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL,
                completed_at TEXT
            )
        """)


def create(task_id: str, description: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO tasks (task_id, description, created_at) VALUES (?,?,?)",
            (task_id, description[:300], _now()),
        )


def set_running(task_id: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE tasks SET status='running', attempts=attempts+1 WHERE task_id=?",
            (task_id,),
        )


def set_done(task_id: str, result: str, *, failed: bool = False) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE tasks SET status=?, result=?, completed_at=? WHERE task_id=?",
            ("failed" if failed else "done", result[:4000], _now(), task_id),
        )


def get_recent(limit: int = 10) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT task_id, description, status, result, created_at, completed_at "
            "FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
