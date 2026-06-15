# ── 빌드 스테이지 ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# 런타임과 동일 경로(/app)에 venv 를 만든다 — 콘솔 스크립트(pytest·ruff·pip-audit)의
# shebang(#!/app/.venv/bin/python)이 런타임에서도 유효하도록 (venv 재배치 깨짐 방지).
WORKDIR /app

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

# git: /commit·/diff·/push 가 워커에서 로컬 git 을 사용
# safe.directory: /workspace 는 호스트 소유 bind-mount 라 git 이 dubious ownership 으로
#   거부함 → system 레벨(/etc/gitconfig)로 예외 등록. read-only FS 에서도 읽기만 하면 됨.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory /workspace

# 보안: root 아닌 전용 유저로 실행
RUN useradd --create-home --no-log-init appuser

# 데이터 디렉터리를 appuser 소유로 미리 생성 — 명명 볼륨(worker-data)이 이 소유권을
# 상속해, non-root 컨테이너가 어떤 플랫폼에서도 sqlite/임베딩 캐시를 쓸 수 있게 한다.
# (바인드마운트와 달리 빈 명명 볼륨은 이미지 디렉터리의 소유권을 복사함)
RUN mkdir -p /app/data && chown appuser:appuser /app/data

USER appuser

# 빌드 스테이지에서 설치된 패키지 복사 (동일 경로 → shebang 유효)
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
# stdout/stderr 즉시 플러시 — docker logs 가 실시간으로 보이도록
ENV PYTHONUNBUFFERED=1

# 소스 복사
COPY app/ ./app/
# scripts: publish_ops 가 발행 export 로직(publish_vault.py)을 재사용 — 이미지에 필요
COPY scripts/ ./scripts/
# vendored last30days 스킬 — recent_research 도구가 호출하는 CLI (서드파티 의존성 없음)
COPY vendor/ ./vendor/

CMD ["python", "-m", "app.main"]

# ── dev/test 스테이지 ─────────────────────────────────────────────────────────
# 프로덕션 이미지(runtime)는 lean 유지. 이 타겟은 dev 도구(ruff·pytest·pip-audit)를
# 포함해 봇의 /lint·/test·/audit 를 컨테이너에서 실행 가능.
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d worker
# dev 의존성을 포함해 venv 재빌드 (builder 재사용, --no-dev 제거)
FROM builder AS builder-dev
RUN uv sync --frozen --no-install-project

FROM runtime AS runtime-dev
# dev 의존성이 포함된 venv 로 교체 (ruff/pytest/pip-audit 바이너리가 /app/.venv/bin 에)
COPY --from=builder-dev /app/.venv /app/.venv
