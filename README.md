# DevOps 자동화 파이프라인

> **Telegram 봇으로 제어하는 LangGraph 멀티 에이전트 DevOps 자동화 파이프라인**
> 자연어 명령 → 게이트웨이가 전문 에이전트로 자동 분기 → ReAct 루프로 작업 수행 → 결과를 Telegram 으로 회신.

Claude API(또는 로컬 vLLM)를 백엔드로, **코드 분석 · 문서 작성 · 인프라 점검 · 트렌드 리서치**를 채팅 한 줄로 위임합니다. 컨테이너 빌드 → 레지스트리 → Kubernetes → 모니터링까지 운영 파이프라인을 함께 제공합니다.

```
Claude Code + Rules + Subagents
  → GitHub → CI (lint·test·build·scan) → GHCR
  → docker-compose / Kubernetes (bot · worker · vLLM)
  → Monitoring (Prometheus · Grafana)
```

---

## 목차

1. [핵심 개념](#핵심-개념)
2. [빠른 시작](#빠른-시작)
3. [아키텍처](#아키텍처)
4. [프로젝트 구조](#프로젝트-구조)
5. [멀티 에이전트 게이트웨이](#멀티-에이전트-게이트웨이)
6. [Telegram 명령어](#telegram-명령어)
7. [6단계 프롬프트 파이프라인](#6단계-프롬프트-파이프라인)
8. [Claude Code 설정 (.claude)](#claude-code-설정-claude)
9. [배포](#배포)
10. [CI/CD](#cicd)
11. [개발 원칙](#개발-원칙)
12. [환경변수](#환경변수)
13. [개발](#개발)

---

## 핵심 개념

이 프로젝트는 4개의 협력 요소로 구성됩니다. 각 요소의 역할이 다르며, 함께 동작해 "채팅 → 작업 수행"을 완성합니다.

| 요소 | 정체 | 책임 |
|------|------|------|
| **Bot** | Telegram 인터페이스 (`:8765`) | 명령 수신·인가, 워커에 작업 위임, 결과 알림 |
| **Worker** | LangGraph 게이트웨이 (`:8766`) | 작업 라우팅, 전문 에이전트 ReAct 루프 실행 |
| **Gateway** | 라우터 + 5개 전문 에이전트 | 작업 유형 판별 → code/doc/infra/stack/general 분기 |
| **Tools** | 에이전트의 손발 | `read_file` · `write_file` · `bash` · `notion_*` |

여기에 **Planner**(복합 작업 분해), **RAG**(Brave 웹 검색 컨텍스트 주입)가 더해집니다.

---

## 빠른 시작

### 1. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 에서 최소 필수 값을 채웁니다.

```env
TELEGRAM_TOKEN=...      # @BotFather 에서 발급
TELEGRAM_CHAT_ID=...    # 본인 chat_id (이 ID 에서만 명령 허용)
CLAUDE_API_KEY=...      # 워커 에이전트 구동에 필요
```

### 2. Docker Compose 로 실행 (로컬 빌드)

```bash
docker compose up --build
```

### 3. 로컬 실행 (개발용)

```bash
uv sync
uv run python -m app.main           # 봇
uv run python -m app.worker.server  # 워커 (별도 터미널)
```

> 다른 PC 에서 **소스 빌드 없이 레지스트리 이미지로** 띄우려면 [배포 §레지스트리 이미지](#b-레지스트리-이미지로-실행-다른-pc) 참고.

---

## 아키텍처

```
[Telegram] ──명령──▶ [Bot :8765]
                         │  작업 위임 (HTTP POST /run)
                         ▼
                  [Worker :8766]
                         │
              ┌──────────┴───────────┐
              │  LangGraph Gateway    │
              │  retrieve → router    │
              └──────────┬───────────┘
            ┌─────┬──────┼──────┬─────────┐
          code   doc   infra  stack   general   ← 전문 에이전트 (ReAct)
            └─────┴──────┼──────┴─────────┘
                         │  도구: read_file/write_file/bash/notion_*
                         ▼  결과 전송 (HTTP POST /worker-result)
                  [Bot] ──응답──▶ [Telegram]
```

- **Bot ↔ Worker** 는 HTTP 로 분리 — 각각 독립 컨테이너로 스케일 가능.
- **중간 진행 상황**은 도구 호출마다 봇 `/notify` 로 실시간 스트리밍.
- **LLM 백엔드**는 `VLLM_ENDPOINT` 설정 시 로컬 vLLM, 없으면 Claude API 로 자동 선택.

---

## 프로젝트 구조

```
devops-pipeline/
├── app/
│   ├── main.py                 # 봇 진입점
│   ├── config.py               # 모든 환경변수 단일 소스
│   ├── bot/                    # Telegram 봇
│   │   ├── server.py           #   HTTP 서버 (/notify, /worker-result)
│   │   ├── notifier.py         #   Telegram 메시지 전송
│   │   └── commands/           #   슬래시 커맨드 핸들러
│   │       ├── system.py       #     /start /help /status /health /model …
│   │       ├── pipeline_cmd.py #     /run (6단계 파이프라인)
│   │       └── worker_cmd.py   #     /task /code /doc /infra /stack …
│   ├── worker/
│   │   ├── server.py           # 워커 HTTP 서버 (/run /tasks /health)
│   │   ├── agent.py            # graph.py 로의 얇은 위임 래퍼
│   │   └── store.py            # SQLite 작업 이력 (data/tasks.db)
│   ├── agent/
│   │   ├── graph.py            # ★ LangGraph 게이트웨이 + 5 에이전트 + Planner
│   │   └── tools.py            # LangChain @tool 래퍼
│   ├── tools/                  # 도구 구현 (권한 가드 포함)
│   │   ├── filesystem.py       #   read_file / write_file (경로 샌드박스)
│   │   ├── shell.py            #   bash (allowlist + 메타문자 차단)
│   │   └── notion.py           #   notion_search / notion_create_page
│   ├── rag/retriever.py        # Brave 웹 검색 컨텍스트
│   ├── notion/                 # Notion API 클라이언트 + 마크다운 변환
│   └── pipeline/runner.py      # /run 파이프라인 (수집→분석→실행)
│
├── prompts/                    # 6단계 자동화 워크플로 프롬프트 세트
│   ├── 00_README.md            #   인덱스
│   ├── 01_analyze.md ~ 06_test.md
│   └── output/                 #   각 단계 산출물 (write_file 대상)
│
├── .claude/                    # Claude Code 협업 설정 (git 추적)
│   ├── settings.json           #   권한 allowlist
│   ├── rules/                  #   boundaries / git-workflow / security
│   └── agents/                 #   code-reviewer / planner / infra-ops
├── CLAUDE.md                   # Claude 행동 지침 (8개 원칙)
│
├── k8s/                        # Kubernetes 매니페스트
│   ├── bot/ worker/ vllm/      #   Deployment · Service · PVC
│   └── monitoring/             #   Prometheus · Grafana
├── monitoring/                 # Prometheus 설정 · Grafana provisioning
│
├── docker-compose.yml          # 로컬 빌드 구동 (+ vllm/monitoring 프로파일)
├── docker-compose.registry.yml # 레지스트리 이미지 override
├── Dockerfile / Dockerfile.vllm
└── .github/workflows/          # ci.yml (lint·test·build·scan·push) · deploy.yml
```

---

## 멀티 에이전트 게이트웨이

[`app/agent/graph.py`](app/agent/graph.py) 의 핵심. 작업이 들어오면 **RAG 컨텍스트 수집 → 라우팅 → 전문 에이전트 실행** 순으로 흐릅니다.

```
START → retrieve(Brave 검색) → router → ┬ code
                                        ├ doc
                                        ├ infra
                                        ├ stack
                                        └ general → END
```

### 라우팅 방식 (2단계)

1. **결정론적 prefix 분기** — 봇 커맨드가 `[CODE_TASK]` 등 prefix 를 붙이면 LLM 호출 없이 즉시 분기.
2. **LLM 분류** — 자유형 요청(`/task`)은 LLM 이 5개 카테고리 중 하나로 분류.

### 전문 에이전트

| 라우트 | 역할 | 사용 도구 |
|--------|------|-----------|
| `code` | 버그·보안·성능 분석, 리팩토링 제안 | `read_file` `write_file` `bash` |
| `doc` | README·API 문서·온보딩 가이드 작성 | `read_file` `write_file` `notion_*` |
| `infra` | Docker·CI/CD·인프라 설정 분석 | `bash` `read_file` `write_file` |
| `stack` | IT 트렌드 리서치 → Notion 저장 (중복 회피) | `notion_search` `notion_create_page` |
| `general` | 위 외 일반 작업 | 전체 도구 |

### Planner

`/plan` 은 별도 StateGraph 로 복합 작업을 **최대 5개 하위 작업으로 분해**한 뒤, 각 하위 작업을 다시 게이트웨이로 순차 실행합니다.

```
START → plan(JSON 분해) → execute(루프) → END
```

---

## Telegram 명령어

> 모든 명령은 `.env` 의 `TELEGRAM_CHAT_ID` 에서만 허용됩니다 (인가 가드).

### 시스템

| 명령 | 설명 |
|------|------|
| `/start` `/help` | 봇 시작 · 명령어 안내 |
| `/status` | CPU / 메모리 / 디스크 |
| `/uptime` | 봇 가동 시간 |
| `/health` | 봇 · 워커 · LLM API 헬스체크 |
| `/model` | 워커 LLM 모델 조회/변경 |

### 작업 위임 (게이트웨이)

| 명령 | 분기 | 설명 |
|------|------|------|
| `/task <설명>` | 자동(LLM 분류) | 자유형 작업 — 게이트웨이가 알아서 라우팅 |
| `/plan <설명>` | Planner | 복합 작업 분해 후 순차 실행 |
| `/code <설명>` | → code | 코드 품질·보안 분석 |
| `/doc <설명>` | → doc | 문서 작성 (Notion 업로드 옵션) |
| `/infra <설명>` | → infra | 인프라/DevOps 설정 점검 |
| `/stack` | → stack | IT 트렌드 리서치 → Notion 페이지 생성 |

### 빠른 도구

| 명령 | 설명 |
|------|------|
| `/run` | 6단계 자동화 파이프라인 실행 (중간 승인 게이트) |
| `/lint` | `ruff check` 실행 후 결과 보고 |
| `/test` | `pytest` 실행 후 통과/실패 보고 |
| `/audit` | `pip-audit` CVE 검사 |
| `/diff` | 마지막 커밋 변경 통계 |
| `/history` | 최근 작업 이력 (SQLite) |
| `/notion` | Notion 연결 상태 진단 |

---

## 6단계 프롬프트 파이프라인

[`prompts/`](prompts/) 는 LLM 코딩 에이전트에게 순서대로 주입하는 **분석 → 리서치 → 설계 → 구현 → 검수 → 테스트** 워크플로입니다. 각 단계는 이전 산출물을 읽고 다음 단계 입력을 만들며, 설계(03)·검수(05)에 사람 승인 게이트가 있습니다.

| # | 단계 | 출력 | 게이트 |
|---|------|------|--------|
| 01 | 프로젝트 진단 | `output/01_analysis_report.md` | 자동 |
| 02 | 트렌드 리서치 | `output/02_research_brief.md` | 자동 |
| 03 | 아키텍처 설계 | `output/03_design_doc.md` | ⏸️ 사람 승인 |
| 04 | 외과적 구현 | 코드 변경 + 로그 | 자체 검증 |
| 05 | 코드 검수 | `output/05_review_report.md` | ⏸️ 사람 승인 |
| 06 | 자동 테스트 | 테스트 보고 + SBOM | 🚦 릴리스 게이트 |

자세한 사용법은 [`prompts/00_README.md`](prompts/00_README.md) 참고.

---

## Claude Code 설정 (.claude)

이 저장소는 **Claude Code 와의 협업 규칙을 코드와 함께 버전 관리**합니다. 어느 환경에서 열어도 동일한 가드레일이 적용됩니다.

| 구성 | 파일 | 역할 |
|------|------|------|
| **행동 지침** | [`CLAUDE.md`](CLAUDE.md) | 8개 핵심 원칙 (아래 [개발 원칙](#개발-원칙)) |
| **경계 규칙** | [`.claude/rules/boundaries.md`](.claude/rules/boundaries.md) | 자동 실행 / 먼저 물어보기 / 절대 금지 |
| **Git 규칙** | [`.claude/rules/git-workflow.md`](.claude/rules/git-workflow.md) | 커밋 타입·메시지 형식 |
| **보안 체크** | [`.claude/rules/security.md`](.claude/rules/security.md) | 커밋 전 시크릿/입력검증 점검 |
| **권한** | [`.claude/settings.json`](.claude/settings.json) | 확인 없이 실행 가능한 명령 allowlist |
| **서브에이전트** | [`.claude/agents/`](.claude/agents/) | code-reviewer · planner · infra-ops |

---

## 배포

### A. 로컬 (docker-compose)

```bash
docker compose up --build                          # bot + worker
docker compose --profile vllm up                   # + 로컬 vLLM (GPU)
docker compose --profile monitoring up             # + Prometheus + Grafana
```

| 서비스 | 포트 | 비고 |
|--------|------|------|
| bot | 8765 | Telegram 인터페이스 |
| worker | 8766 | 내부 전용 (expose) |
| vLLM | 8000 | `--profile vllm`, GPU 필요 |
| Prometheus | 9090 | `--profile monitoring` |
| Grafana | 3000 | `--profile monitoring` |

### B. 레지스트리 이미지로 실행 (다른 PC)

CI 가 GHCR 에 발행한 이미지를 받아 소스 빌드 없이 구동합니다. ([`docker-compose.registry.yml`](docker-compose.registry.yml) 가 `build:` 를 이미지로 override)

```bash
git clone https://github.com/currentJob/devops-pipeline.git && cd devops-pipeline
cp .env.example .env                               # 실제 토큰 입력

echo $CR_PAT | docker login ghcr.io -u <github-username> --password-stdin

docker compose -f docker-compose.yml -f docker-compose.registry.yml --profile monitoring pull
docker compose -f docker-compose.yml -f docker-compose.registry.yml --profile monitoring up -d
```

> compose 파일·모니터링 설정·워커 작업 디렉토리는 호스트에서 마운트되므로 저장소 클론이 필요합니다.
> 이미지 경로/태그는 `.env` 의 `APP_IMAGE` 로 변경할 수 있습니다.

### C. Kubernetes

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
bash k8s/create-secrets.sh                          # 시크릿 생성 (커밋 금지)
kubectl apply -f k8s/bot/ -f k8s/worker/
kubectl apply -f k8s/monitoring/                    # 선택
kubectl apply -f k8s/vllm/                          # GPU 노드 있을 때만
```

> 배포 전 `k8s/**/deployment.yaml` 의 `YOUR_ORG` 플레이스홀더를 실제 org 로 치환하세요.

---

## CI/CD

`.github/workflows/` 의 두 워크플로가 검증과 배포를 분리합니다.

### `ci.yml` — push/PR 자동

| Job | 트리거 | 동작 |
|-----|--------|------|
| `lint-test` | 모든 push/PR | ruff check · ruff format · pytest · pip-audit |
| `container-build-scan` | 모든 push/PR | 이미지 빌드 · SBOM(CycloneDX/SPDX) · Trivy 스캔 |
| `registry-push` | push 만 | GHCR 에 앱 이미지 푸시 (semver 태그) |
| `vllm-build` | main/태그 push | GHCR 에 vLLM 이미지 푸시 |

### `deploy.yml` — 수동 (`workflow_dispatch`)

staging/production 선택 후 `kubectl set image` 로 롤링 배포 + Telegram 알림. **자동 배포는 일어나지 않습니다.**

---

## 개발 원칙

[`CLAUDE.md`](CLAUDE.md) 의 8개 원칙이 작업 방식을 규율합니다.

1. **Think Before Coding** — 가정을 명시하고, 모호하면 먼저 질문.
2. **Simplicity First** — 문제를 푸는 최소 코드. 투기적 추상화 금지.
3. **Surgical Changes** — 요청과 무관한 인접 코드를 "개선"하지 않음.
4. **Goal-Driven Execution** — 검증 가능한 완료 기준을 세우고 루프.
5. **Language** — 내부 추론은 영어, 응답은 한국어.
6. **Scope Clarification** — 파일 3개+·새 의존성·모호한 요구는 착수 전 확인.
7. **Plan Mode** — 복잡한 변경은 계획 먼저.
8. **Extended Guidelines** — `.claude/rules/` 가 위 원칙을 확장.

### 경계 (boundaries)

| ✅ 자동 실행 | ⚠️ 먼저 확인 | 🚫 절대 금지 |
|-------------|-------------|-------------|
| 린트·테스트·타입 추가 | 파일 삭제 · `git push` | 시크릿 하드코딩 |
| 읽기 전용 탐색 | 새 의존성 추가 | `main` 강제 푸시 |
| 내 변경의 정리 | 스키마/포트/API 변경 | `data/tasks.db` 커밋 |

---

## 환경변수

| 변수 | 필수 | 기본값 | 설명 |
|------|:----:|--------|------|
| `TELEGRAM_TOKEN` | ✅ | — | Telegram Bot API 토큰 |
| `TELEGRAM_CHAT_ID` | ✅ | — | 허용할 Chat ID |
| `CLAUDE_API_KEY` | ▲ | — | 워커 에이전트 구동에 필요 (vLLM 사용 시 불필요) |
| `APPROVAL_TIMEOUT` | | `300` | `/run` 승인 대기(초) |
| `LOG_LEVEL` | | `INFO` | 로그 레벨 |
| `NOTION_TOKEN` | | — | `/stack` `/doc` Notion 업로드용 |
| `NOTION_PARENT_PAGE_ID` | | — | Notion 부모 페이지 ID |
| `BRAVE_API_KEY` | | — | RAG 웹 검색용 |
| `WORKER_MODEL` | | `claude-sonnet-4-6` | 워커 Claude 모델 |
| `WORKER_MAX_TOKENS` | | `8192` | 최대 토큰 |
| `WORKER_MAX_ITERATIONS` | | `10` | ReAct 최대 반복 |
| `WORKER_TIMEOUT_S` | | `120` | 작업 타임아웃(초) |
| `VLLM_ENDPOINT` | | — | 설정 시 Claude 대신 vLLM 사용 |
| `VLLM_MODEL` | | `Qwen/Qwen2.5-Coder-7B-Instruct` | vLLM 서빙 모델 |
| `APP_IMAGE` | | `ghcr.io/currentjob/devops-pipeline:latest` | 레지스트리 실행 시 이미지 |
| `GRAFANA_ADMIN_PASSWORD` | | `changeme` | Grafana 관리자 비밀번호 |

전체 목록은 [`.env.example`](.env.example) 참고.

---

## 개발

```bash
uv sync                      # 의존성 설치
uv run pytest tests/ -v      # 테스트
uv run ruff check .          # 린트
uv run ruff format .         # 포맷
uv run pip-audit             # 보안 감사
uv run pre-commit install    # pre-commit 훅 설치
```

| 요구사항 | 버전 |
|----------|------|
| Python | 3.12+ |
| uv | latest |
| Docker + Compose | v2.24.4+ (`!reset` 문법) |
