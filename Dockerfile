# ── 빌드 스테이지 ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
# 의존성만 먼저 설치 (캐시 활용)
RUN uv sync --no-dev --no-install-project

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
