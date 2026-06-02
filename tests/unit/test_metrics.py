"""워커 /metrics 노출 핸들러 단위 테스트 (네트워크 불필요)."""

from __future__ import annotations

from app.worker import metrics


async def test_metrics_endpoint_exposes_counters():
    metrics.TASKS_TOTAL.labels(status="done").inc()
    resp = await metrics.handle_metrics(None)

    assert resp.status == 200
    assert "text/plain" in resp.headers["Content-Type"]
    body = resp.body.decode()
    assert "worker_tasks_total" in body
    assert "worker_task_duration_seconds" in body
    assert "worker_inflight" in body
    assert "worker_queue_size" in body
