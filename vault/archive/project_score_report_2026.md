---
title: "프로젝트 인프라/DevOps 종합 점수 보고서"
date: 2026-06-04
tags: [migrated]
source: migrated
---

# 프로젝트 인프라/DevOps 종합 점수 보고서
> 분석 기준일: 2026-06-04  
> 대상: Telegram 승인 기반 자동화 파이프라인 (LangGraph + Claude/vLLM + K8s)  
> 비교 기준: 2025~2026 업계 모범 사례 (CNCF, GitHub Actions, Supply Chain Security, OCI 표준)

---

## 📊 종합 점수표

| # | 기능 영역 | 점수 | 등급 | 한 줄 요약 |
|---|-----------|------|------|-----------|
| 1 | **패키지 관리 (uv / pyproject.toml)** | 95/100 | ⭐ S | 2026 최신 스택 완벽 적용 |
| 2 | **Dockerfile / 컨테이너 보안** | 88/100 | ⭐ A+ | multi-stage·non-root·read_only 우수 |
| 3 | **docker-compose 구성** | 85/100 | ⭐ A | profiles·healthcheck·overlay 패턴 우수 |
| 4 | **CI 파이프라인 (GitHub Actions)** | 91/100 | ⭐ S | SBOM·Trivy·pip-audit·concurrency 완비 |
| 5 | **CD / 배포 파이프라인** | 72/100 | B+ | 기본 구조 양호, GitOps 부재 |
| 6 | **Kubernetes 매니페스트** | 78/100 | B+ | 보안 컨텍스트 우수, HPA/NetworkPolicy 미비 |
| 7 | **시크릿 / 설정 관리** | 70/100 | B | gitleaks 도입, K8s Secret 자동화 미흡 |
| 8 | **모니터링 / 가관찰성** | 74/100 | B+ | Prometheus + Grafana 구비, 트레이싱 부재 |
| 9 | **코드 품질 / 린트** | 93/100 | ⭐ S | ruff·pre-commit·strict 설정 최신 수준 |
| 10 | **테스트 커버리지 구조** | 68/100 | B | 단위 테스트 다양, 통합·E2E 미구비 |

**종합 평균: 81.4 / 100 — 등급 A (업계 상위 ~20% 수준)**

---

## 1. 패키지 관리 — 95/100 ⭐ S

### 잘 된 점
- `uv` + `pyproject.toml` 완전 이관 → 2025~2026 Python 생태계 표준 완벽 채택
- `uv.lock` 커밋으로 결정론적 빌드 보장
- `requires-python = ">=3.12"` 명시 → 타입 힌트·`asyncio` 최신 기능 활용
- `[dependency-groups] dev` 분리 → prod 이미지에 dev 패키지 미포함
- `pip-audit` dev 의존성 포함 → 취약점 자동 스캔

### 개선 여지
- `pyproject.toml` 에 `[project.scripts]` 가 `start = "app.main:main"` 하나뿐 → `worker` 엔트리포인트도 추가 권장
- `ruff>=0.14.0` 지정이지만 pre-commit 은 `v0.15.13` 핀 → 버전 불일치 가능, 동기화 필요

---

## 2. Dockerfile / 컨테이너 보안 — 88/100 ⭐ A+

### 잘 된 점
```
builder(python:3.12-slim) → runtime(python:3.12-slim)
```
- **Multi-stage build**: 빌드 도구 미포함, 이미지 경량화
- **Non-root user**: `useradd appuser`, `USER appuser` 적용
- `PYTHONUNBUFFERED=1` → docker logs 실시간 노출
- `docker-compose.yml` 에서 `read_only: true` + `tmpfs: /tmp` → 컨테이너 파일시스템 불변성 확보
- `no-new-privileges:true` → 권한 상승 차단

### 개선 여지
- **이미지 다이제스트 핀**: `FROM python:3.12-slim` → `FROM python:3.12-slim@sha256:...` 권장 (Supply Chain 공격 방어)
- **HEALTHCHECK 누락**: Dockerfile 자체에 `HEALTHCHECK` 미정의 (compose 에서만 정의됨)
- **`COPY app/ ./app/`**: `.dockerignore` 가 간단한 수준 → `__pycache__`, `*.pyc`, `tests/` 제외 항목 보강 권장
- **Dockerfile.vllm**: `FROM vllm/vllm-openai:latest` — `latest` 태그는 재현성 위험, 버전 핀 필요

---

## 3. docker-compose 구성 — 85/100 ⭐ A

### 잘 된 점
- **profiles 패턴**: `postgres`, `vllm`, `monitoring` 선택적 활성화 → 2024+ Compose best practice
- **docker-compose.registry.yml overlay**: `build: !reset null` 사용 → Compose v2 override 패턴 정확히 적용
- **내부 네트워크 전용**: postgres `expose`만 사용, 호스트 미노출
- **`127.0.0.1` 바인딩**: 모든 외부 포트를 `127.0.0.1:xxxx:xxxx` — 로컬호스트 전용 노출
- **healthcheck** 전 서비스 구성 (worker → bot `depends_on: condition: service_healthy`)
- **vLLM `deploy.resources.reservations`**: GPU 리소스 선언 명확

### 개선 여지
- **worker 볼륨**: `./:/workspace:rw` — 호스트 전체 마운트는 보안 리스크, `/workspace` 범위 최소화 필요
- **secrets 관리**: `env_file: .env` 직접 주입 → Docker Swarm/Compose `secrets:` 블록 미사용
- **restart policy**: 서비스에 `restart: unless-stopped` 미정의 → 컨테이너 크래시 시 자동 재시작 없음
- **vllm 이미지 태그**: `vllm/vllm-openai:latest` → 버전 핀 권장

---

## 4. CI 파이프라인 — 91/100 ⭐ S

### 잘 된 점
```
lint-test → container-build-scan → registry-push
```
- **3단계 순차 게이트**: 린트 실패 시 빌드 미진행
- **concurrency + cancel-in-progress**: 중복 CI 실행 자동 취소
- **GHA 캐시**: `cache-from/to: type=gha,mode=max` → 레이어 캐시 최대화
- **SBOM 이중 생성**: CycloneDX + SPDX 두 포맷 아티팩트 저장 → Supply Chain 규정 대응
- **Trivy 이중 스캔**: CRITICAL(빌드 실패) / HIGH(SARIF 보고) 분리 → 실용적 정책
- **pip-audit --strict**: Python 의존성 CVE 차단
- **GHCR 멀티 태그**: `latest`, `branch`, `semver`, `sha` 동시 발행

### 개선 여지
- **`astral-sh/setup-uv@v3`의 `version: "latest"`**: CI 재현성을 위해 버전 핀 권장 (`version: "0.5.x"`)
- **테스트 커버리지 리포트**: `pytest --cov` + `coverage` 아티팩트 업로드 미구성
- **PR 라벨/체인지로그 자동화**: `release-drafter` 또는 `semantic-release` 미적용
- **Trivy DB 캐시**: `cache-dir` 미설정 → 매 실행마다 DB 재다운로드

---

## 5. CD / 배포 파이프라인 — 72/100 B+

### 잘 된 점
- `workflow_dispatch` + `environment` 입력 → 수동 환경 선택 배포
- **Telegram 배포 알림** (성공/실패 분기) → 즉각적인 피드백 루프
- GPU 노드 존재 여부 동적 감지 후 vLLM 조건부 배포
- `kubectl rollout status --timeout` → 배포 완료 확인 게이트
- **concurrency(cancel-in-progress: false)**: 배포는 취소 안 함 → 안전한 설계

### 개선 여지
- **GitOps 부재**: ArgoCD / Flux 미사용 → `kubectl set image` 명령형 방식은 2024+ 기준 레거시
- **staging → production 자동 프로모션**: 파이프라인 없음, 수동 dispatch만 존재
- **Rollback 자동화**: 실패 시 `kubectl rollout undo` 미구현
- **K8s Secret 배포**: `create-secrets.sh` 스크립트에 의존 → Sealed Secrets / External Secrets Operator 미도입
- **배포 전 스모크 테스트**: 이미지 pull 후 기능 검증 단계 없음

---

## 6. Kubernetes 매니페스트 — 78/100 B+

### 잘 된 점
- **SecurityContext 완비** (bot, worker):
  ```yaml
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities: drop: ["ALL"]
  seccompProfile: RuntimeDefault
  ```
- **Resources 요청/제한** 전 서비스 정의
- **liveness + readiness 프로브** 분리 구성
- **vLLM GPU 노드**: `nodeSelector`, `tolerations`, `/dev/shm` Memory emptyDir 설정 정확
- **Namespace 분리**: `devops-pipeline` 독립 네임스페이스

### 개선 여지
- **HPA(Horizontal Pod Autoscaler) 미정의**: worker 부하 증가 시 수동 스케일만 가능
- **NetworkPolicy 미구현**: Pod 간 통신 무제한 → 최소 권한 네트워크 정책 필요
- **PodDisruptionBudget 미정의**: 노드 드레인 시 서비스 중단 가능
- **vLLM SecurityContext**: bot/worker 대비 보안 컨텍스트 미정의
- **Ingress 미정의**: 외부 노출 방법 매니페스트에 없음
- **bot livenessProbe**: `python -c "import app.config"` → 실질적 liveness 측정 불가, HTTP 체크 권장

---

## 7. 시크릿 / 설정 관리 — 70/100 B

### 잘 된 점
- **gitleaks** pre-commit 훅 → 커밋 시점 시크릿 유출 차단
- `.env.example` 완비 → 온보딩 가이드 제공
- `.gitignore` 에 `.env` 명시적 제외
- `detect-private-key` pre-commit 훅 추가
- K8s: `secretRef: pipeline-secrets` 분리 참조

### 개선 여지
- **`.env` 파일이 루트에 존재** (퍼미션 rwxrwxrwx) → 운영 환경에서 매우 위험
- **K8s Secret 생성**: `create-secrets.sh` 쉘 스크립트 의존 → **External Secrets Operator** (AWS Secrets Manager / Vault 연동) 미도입
- **시크릿 로테이션 정책 없음**: TELEGRAM_TOKEN, CLAUDE_API_KEY 만료/교체 절차 미문서화
- **POSTGRES_PASSWORD 기본값 `changeme`**: configmap.yaml 에 하드코딩 위험

---

## 8. 모니터링 / 가관찰성 — 74/100 B+

### 잘 된 점
- **Prometheus + Grafana** 스택 docker-compose `monitoring` profile 구성
- **커스텀 메트릭 4종**: `TASKS_TOTAL(Counter)`, `TASK_DURATION(Histogram)`, `INFLIGHT(Gauge)`, `QUEUE_SIZE(Gauge)` — 실용적 설계
- **LLM 특화 히스토그램 버킷**: `(1,2,5,10,30,60,120,300)` → AI 작업 지연 분포 측정 최적화
- **vLLM `/metrics` 자동 연동**: prometheus.yml 에 vllm job 포함
- **K8s monitoring 매니페스트**: grafana.yaml, prometheus.yaml 분리 관리

### 개선 여지
- **분산 추적(Tracing) 부재**: OpenTelemetry 미도입 → LangGraph 에이전트 내 체인 추적 불가
- **Grafana 대시보드 코드화**: 현재 수동 설정 추정 → `grafana-dashboard-configmap` 미구성
- **알림 규칙(AlertManager) 미정의**: 지표 이상 시 알림 없음 (Telegram 알림은 배포 레벨만)
- **로그 집계 스택 부재**: Loki / ELK 미도입 → `docker logs` 수준 의존
- **Bot 서비스 `/metrics` 미노출**: worker 만 prometheus 스크레이프 대상

---

## 9. 코드 품질 / 린트 — 93/100 ⭐ S

### 잘 된 점
- **ruff 2026 권장 룰셋**: `E,F,I,B,UP,SIM` — pycodestyle+flakes+isort+bugbear+upgrade+simplify 통합
- **pre-commit 훅 완비**: trailing-whitespace, end-of-file, yaml/toml 검증, merge-conflict, large-files
- **`target-version = "py312"`**: 최신 파이썬 문법 업그레이드 자동화 (UP 룰)
- **`line-length = 100`**: 현대적 기준 (PEP8 79자 → 현업 100~120자 추세)
- **`tests/**` per-file-ignores**: 테스트 전용 예외 처리
- `ruff-format` (Black 대체) pre-commit 통합

### 개선 여지
- **`mypy` / `pyright` 미적용**: 타입 체크 없음 → Python 3.12 + async 코드에서 런타임 타입 오류 위험
- **pre-commit ruff 버전(`v0.15.13`)과 pyproject.toml(`>=0.14.0`) 불일치**: 동기화 필요
- **`bandit` 보안 린트 미적용**: SAST 도구 공백 (CI의 Trivy는 이미지 레벨만)

---

## 10. 테스트 커버리지 구조 — 68/100 B

### 잘 된 점
- **단위 테스트 10종** 구성: agent_hardening, git_ops, llm_backend, metrics, notify, notion_client, security_audit, task_memory, tools
- `pytest-asyncio` + `asyncio_mode = "auto"` → 비동기 테스트 자동화
- `--strict-markers` → 마커 오타 방지
- `-ra` 플래그 → 실패/스킵 요약 자동 출력

### 개선 여지
- **통합 테스트 없음**: bot ↔ worker HTTP 통신, DB 저장/조회 E2E 흐름 미검증
- **`pytest --cov` 미적용**: 커버리지 측정 불가 → CI에서 커버리지 게이트 없음
- **테스트 픽스처 분리**: `tests/unit/conftest.py` 미확인이나 공통 픽스처 체계화 필요
- **`test_telegram.py` 루트 위치**: `tests/` 외부에 테스트 파일 존재 → pytest 경로 불일치

---

## 🔴 최우선 개선 권고 (TOP 5)

| 순위 | 항목 | 영향도 | 난이도 |
|------|------|--------|--------|
| 1 | **worker `./:/workspace:rw` 마운트 범위 최소화** | 보안 HIGH | 낮음 |
| 2 | **`restart: unless-stopped` 정책 추가** | 가용성 HIGH | 매우 낮음 |
| 3 | **K8s NetworkPolicy 정의** | 보안 HIGH | 중간 |
| 4 | **pytest-cov 적용 + CI 커버리지 게이트** | 품질 MEDIUM | 낮음 |
| 5 | **External Secrets Operator 또는 Sealed Secrets 도입** | 보안 HIGH | 중간 |

---

## 🟡 중기 개선 권고 (3개월 이내)

- ArgoCD / Flux GitOps 전환으로 CD 성숙도 향상
- OpenTelemetry SDK 통합 (LangGraph 트레이싱)
- HPA 정의 (worker CPU/메모리 기반 자동 스케일)
- AlertManager 알림 룰 정의
- `mypy --strict` 또는 `pyright` CI 통합
- Dockerfile 이미지 다이제스트 핀

---

*이 보고서는 prompts/output/project_score_report_2026.md 에 저장되었습니다.*
