"""워커 Prometheus 지표 정의 + 노출 핸들러.

Prometheus 가 worker:8766/metrics 를 스크레이프한다 (monitoring/prometheus.yml).
server.py 가 작업 처리 경로에서 아래 지표를 갱신한다.
"""

from __future__ import annotations

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# 작업 완료 수 (status=done|failed)
TASKS_TOTAL = Counter("worker_tasks_total", "처리 완료한 작업 수", ["status"])

# 작업 처리 시간(초) — LLM 작업 특성에 맞춘 버킷
TASK_DURATION = Histogram(
    "worker_task_duration_seconds",
    "작업 처리 시간(초)",
    buckets=(1, 2, 5, 10, 30, 60, 120, 300),
)

# 현재 동시에 처리 중인 작업 수
INFLIGHT = Gauge("worker_inflight", "현재 처리 중인 작업 수")

# 대기 큐 길이
QUEUE_SIZE = Gauge("worker_queue_size", "대기 큐에 쌓인 작업 수")


async def handle_metrics(_request: web.Request) -> web.Response:
    """Prometheus 노출 포맷으로 현재 지표를 반환."""
    return web.Response(body=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
