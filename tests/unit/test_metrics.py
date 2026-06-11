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


async def test_metrics_exposes_route_backend_labels():
    metrics.ROUTE_TOTAL.labels(route="code", backend="Claude").inc()
    metrics.ROUTE_DURATION.labels(route="code").observe(1.2)
    resp = await metrics.handle_metrics(None)
    body = resp.body.decode()
    assert "worker_route_total" in body
    assert 'route="code"' in body
    assert 'backend="Claude"' in body
    assert "worker_route_duration_seconds" in body
