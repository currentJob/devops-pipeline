# ── 빌드 스테이지 ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir uv

# 느린 PyPI 응답에 대한 내성 (기본 30s → 120s). uv 는 실패 시 자동 재시도.
ENV UV_HTTP_TIMEOUT=120

# lock 파일까지 복사해 --frozen 으로 재현 가능 설치 (CI 와 동일, 재해석 네트워크 부하 감소)
COPY pyproject.toml uv.lock ./
# 의존성만 먼저 설치 (레이어 캐시 활용)
RUN uv sync --frozen --no-dev --no-install-project

# ── 실행 스테이지 ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# git: /commit 명령이 워커에서 로컬 git 커밋을 수행하는 데 필요 (push 미사용)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# 보안: root 아닌 전용 유저로 실행
RUN useradd --create-home --no-log-init appuser
USER appuser

# 빌드 스테이지에서 설치된 패키지 복사
COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
# stdout/stderr 즉시 플러시 — docker logs 가 실시간으로 보이도록
ENV PYTHONUNBUFFERED=1

# 소스 복사
COPY app/ ./app/
# vendored last30days 스킬 — recent_research 도구가 호출하는 CLI (서드파티 의존성 없음)
COPY vendor/ ./vendor/

CMD ["python", "-m", "app.main"]
