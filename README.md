# DevOps 자동화 파이프라인

> **Telegram 봇으로 제어하는 멀티 에이전트 DevOps 자동화 파이프라인** (LangGraph 오케스트레이션 · Anthropic Agent SDK / openai SDK)
> 자연어 명령 → 게이트웨이가 전문 에이전트로 자동 분기 → 도구 사용(tool-use) 루프로 작업 수행 → 결과를 Telegram 으로 회신.

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
| **Worker** | 게이트웨이 (`:8766`) | 작업 라우팅, 전문 에이전트 도구 사용(tool-use) 루프 실행 |
| **Gateway** | 라우터 + 6개 전문 에이전트 | 작업 유형 판별 → code/doc/infra/stack/poc/general 분기 |
| **Tools** | 에이전트의 손발 | `read_file` · `write_file` · `bash` · `recent_research` · `vault_*` |
| **Qdrant** | 벡터 DB (`:6333`, 내부) | vault 노트 임베딩 저장 → `vault_search` 의미 검색 |

여기에 **Planner**(복합 작업 분해), **PoC Autopilot**(LangGraph 빌드→수정→평가 루프), **RAG**(Brave 웹 검색 컨텍스트 주입)가 더해집니다.

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
              ┌──────────────────────────┐
              │  LangGraph Gateway        │
              │  retrieve → route → exec  │
              └──────────┬───────────────┘
        ┌─────┬─────┬──────┬─────┬─────┬─────────┐
       code  doc  infra  stack  poc  general   ← 전문 에이전트 (tool-use)
        └─────┴─────┴──────┴─────┴─────┴─────────┘
                         │  도구: read_file/write_file/bash/recent_research/vault_*
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
│   │       ├── pipeline_cmd.py #     /run (의존성 보안 감사 파이프라인)
│   │       └── worker_cmd.py   #     /task /code /doc /infra /stack …
│   ├── worker/
│   │   ├── server.py           # 워커 HTTP 서버 (/run /poc/autopilot /poc/eval /git/* /vault/* /digest)
│   │   ├── agent.py            # graph.py 로의 얇은 위임 래퍼
│   │   ├── git_ops.py          #   /commit·/push (site/content 한정 스테이징)
│   │   ├── publish_ops.py      #   /notes 발행 토글·export
│   │   ├── digest.py           #   주간 브리핑 노트 생성
│   │   ├── selfcheck.py        #   런타임 의존성 자가점검
│   │   ├── metrics.py          #   Prometheus 메트릭
│   │   └── store.py            # 작업 이력 DB (SQLite 기본 / Postgres 선택, DB_BACKEND)
│   ├── agent/
│   │   ├── graph.py            # ★ LangGraph 게이트웨이(retrieve→route→execute) + 6 에이전트 + Planner
│   │   ├── runtime.py          # LLM 런타임 (Claude=Agent SDK tool_runner / vLLM=openai) + tool-use 루프
│   │   ├── sdk_tools.py        #   Anthropic Agent SDK 도구 정의 (@beta_async_tool → app.tools.execute)
│   │   └── outcome.py          # 작업 결과 값 객체 (성공/실패)
│   ├── tools/                  # 도구 구현 (권한 가드 포함)
│   │   ├── filesystem.py       #   read_file / write_file (경로 샌드박스)
│   │   ├── shell.py            #   bash (allowlist + 메타문자 차단)
│   │   ├── obsidian.py         #   vault_search / vault_save (Obsidian 노트)
│   │   └── research.py         #   recent_research (last30days 최신 조사)
│   ├── rag/
│   │   ├── retriever.py        #   Brave 웹 검색 컨텍스트
│   │   └── vault_index.py      #   Qdrant + fastembed 벡터 인덱스 (의미 검색)
│   └── pipeline/               # /run·PoC 파이프라인
│       ├── runner.py           #   /run: 의존성 보안 감사 (OSV→AI 분석→교정 리포트)
│       ├── security_audit.py   #   OSV 스캔·리포트 빌더
│       ├── poc_pipeline.py     #   /pocrun autopilot (LangGraph 빌드→수정→평가 루프)
│       └── poc_eval.py         #   PoC 평가 (정적지표+LLM→EVALUATION.md)
│
├── prompts/                    # 6단계 자동화 워크플로 프롬프트 세트
│   ├── 00_README.md            #   인덱스
│   ├── 01_analyze.md ~ 06_test.md
│   └── output/                 #   각 단계 산출물 (write_file 대상)
│
├── vault/                      # Obsidian 지식 vault (워커가 .md 노트 생성, vault_save 대상)
│
├── .claude/                    # Claude Code 협업 설정 (git 추적)
│   ├── settings.json           #   권한 allowlist
│   ├── rules/                  #   boundaries / git-workflow / security
│   └── agents/                 #   code-reviewer / planner / infra-ops
├── CLAUDE.md                   # Claude 행동 지침 (9개 원칙)
│
├── k8s/                        # Kubernetes 매니페스트
│   ├── bot/ worker/ vllm/      #   Deployment · Service · PVC
│   └── monitoring/             #   Prometheus · Grafana
├── monitoring/                 # Prometheus 설정 · Grafana provisioning
│
├── docker-compose.yml          # 로컬 빌드 구동 (+ vllm/monitoring 프로파일)
├── docker-compose.registry.yml # 레지스트리 이미지 override
├── Dockerfile / Dockerfile.vllm
├── site/                       # vault → 기술 블로그(Quartz) 설정 (quartz.config.ts)
└── .github/workflows/          # ci.yml · deploy.yml · blog.yml (vault 발행)
```

---

## 멀티 에이전트 게이트웨이

[`app/agent/graph.py`](app/agent/graph.py) 의 핵심. 작업이 들어오면 **RAG 컨텍스트 수집 → 라우팅 → 전문 에이전트 실행** 순으로 흐릅니다.

```
START → retrieve(Brave 검색) → router → ┬ code
                                        ├ doc
                                        ├ infra
                                        ├ stack
                                        ├ poc
                                        └ general → END
```

### 라우팅 방식 (2단계)

1. **결정론적 prefix 분기** — 봇 커맨드가 `[CODE_TASK]` 등 prefix 를 붙이면 LLM 호출 없이 즉시 분기.
2. **LLM 분류** — 자유형 요청(`/task`)은 LLM 이 5개 카테고리 중 하나로 분류.

### 전문 에이전트

| 라우트 | 역할 | 사용 도구 |
|--------|------|-----------|
| `code` | 버그·보안·성능 분석, 리팩토링 제안 | `read_file` `write_file` `bash` |
| `doc` | README·API 문서·온보딩 가이드 작성 | `read_file` `write_file` `recent_research` `vault_*` |
| `infra` | Docker·CI/CD·인프라 설정 분석 | `bash` `read_file` `write_file` |
| `stack` | IT 트렌드 리서치 → Obsidian vault 저장 (중복 회피) | `recent_research` `vault_search` `vault_save` |
| `poc` | 호환 서비스 조합 → end-to-end PoC 스캐폴드 생성 | `recent_research` `vault_search` `read_file` `write_file` |
| `general` | 위 외 일반 작업 | 전체 도구 |

> 내부 라우트 `pocfix`(read_file·write_file 한정)는 PoC autopilot 의 빌드 실패 수정 단계에서만 사용됩니다(아래 [PoC 자동 파이프라인](#poc-자동-파이프라인-autopilot)).

### Planner

`/plan` 은 별도 분해 단계로 복합 작업을 **최대 5개 하위 작업으로 분해**한 뒤, 각 하위 작업을 다시 게이트웨이로 순차 실행합니다.

```
START → plan(JSON 분해) → execute(루프) → END
```

### PoC 자동 파이프라인 (autopilot)

`/pocrun <slug>` 은 [`app/pipeline/poc_pipeline.py`](app/pipeline/poc_pipeline.py) 의 **LangGraph StateGraph** 로, 생성된 PoC 를 격리 환경에서 자동으로 빌드·수정·평가합니다. 확인 1회가 최대 `POC_AUTOPILOT_MAX_ITERATIONS` 회 격리 실행을 인가합니다.

```
START → build ──(성공)──────────────▶ evaluate → END
          │  └(빌드/실행 실패·여유)──▶ fix ─▶ (build 로 복귀)
          │  └(보안 정적검사 위반)─────▶ evaluate(미통과) → END
          └(반복 소진)────────────────▶ evaluate(미통과) → END
```

- **build** — `pocsandbox` 사이드카(`/run`)가 정적검사 + 무-egress(`--network none`) + 자원캡으로 격리 빌드/실행.
- **fix** — 빌드 실패 시 `pocfix` 라우트 에이전트가 빌드 로그를 보고 `prompts/output/poc/<slug>/` **한정**으로 소스 수정(보안 설정 변경 금지).
- **evaluate** — `poc_eval.evaluate` 로 `EVALUATION.md` 생성(정적지표 + LLM 종합 + 자동 수정 이력).

> 제어 흐름은 게이트웨이와 동일한 LangGraph StateGraph 이고 LLM 호출은 `runtime`(Claude=Agent SDK / vLLM 폴백)을 재사용합니다. **보안 정적검사 위반(stage=check)은 자동 수정하지 않고 즉시 종료**해 우회를 차단합니다.

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
| `/doc <설명>` | → doc | 문서 작성 (Obsidian vault 저장) |
| `/infra <설명>` | → infra | 인프라/DevOps 설정 점검 |
| `/stack` | → stack | IT 트렌드 리서치 → Obsidian vault 노트 생성 |
| `/poc [테마]` | → poc | 호환 서비스 조합 → `prompts/output/poc/<slug>/` 에 PoC 스캐폴드 생성 (결과에 **자동 빌드·평가 버튼** 첨부) |
| `/pocs` | worker | 생성된 PoC 목록 조회 (파일 수·평가/핸드오프 유무) |
| `/pocrun <slug>` | autopilot | PoC 를 **격리 빌드 → 실패 시 자동 수정 → 재빌드 반복 → 평가**(LangGraph). 확인 1회로 최대 N회 실행 → `EVALUATION.md` |

> `/poc` 는 워커 샌드박스 안에서 **스캐폴드(파일)만 생성**합니다(빌드·실행 안 함). 생성 직후 봇이 **"▶️ 자동 빌드·평가" 버튼**을 띄우며(또는 `/pocrun <slug>`), 탭하면 autopilot 파이프라인이 시작됩니다.
>
> 🧪 `/pocrun` (autopilot)은 **격리 빌드 → 실패 시 자동 수정 → 재빌드 반복 → 평가**를 한 흐름으로 수행합니다. 빌드 실패 시 worker 가 빌드 로그를 보고 `prompts/output/poc/<slug>/` 소스를 수정한 뒤 재빌드하며(최대 `POC_AUTOPILOT_MAX_ITERATIONS` 회), 성공/소진 시 `EVALUATION.md`(정적지표 + LLM 종합 + 자동 수정 이력)를 생성합니다. 평가 본체는 PoC 파일에 접근 가능한 **worker** 가 수행합니다(bot 은 read-only).
>
> ⚠️ `/pocrun` 은 **LLM 생성 코드를 실행**합니다(임의 코드 실행). 확인 1회가 최대 N회 격리 실행을 인가하며, `docker.sock` 을 `pocsandbox` 사이드카에만 격리하고 매 재빌드도 정적검사+무-egress(`--network none`)+자원캡+자동 teardown 을 거칩니다. **보안 정적검사 위반은 자동 수정하지 않습니다.** 잔여 위험은 [security.md](.claude/rules/security.md). 사용 전 사이드카 기동 필요: `docker compose --profile poc up -d pocsandbox`

### 빠른 도구

| 명령 | 설명 |
|------|------|
| `/run` | 의존성 보안 감사 파이프라인 (OSV 스캔 → AI 분석 → 교정 리포트, 승인 게이트) |
| `/ci` | 로컬 CI 통합 — `ruff check` + `pytest` + `pip-audit` 를 한 번에 실행해 통합 리포트 |
| `/diff` | 마지막 커밋 변경 통계 |
| `/commit` | 변경 내역으로 커밋 메시지 생성 → 미리보기 → 확인 시 로컬 커밋 (push 안 함) |
| `/push` | 현재 브랜치를 origin 으로 push (미리보기 → 확인 버튼) |
| `/history` | 최근 작업 이력 (SQLite) |
| `/reindex` | vault 노트 재인덱싱 + MOC/Dashboard 노트 갱신 |
| `/digest` | 최근 vault 노트를 요약한 주간 브리핑 노트 생성 |
| `/notes` | vault 노트 발행(✅)/비공개(⬜) 토글 → `🚀 발행 적용`(export+commit+push, 확인 후) |

> ⚠️ `/ci` 는 dev 도구(ruff·pytest·pip-audit)가 필요합니다. 프로덕션
> 워커 이미지(`runtime`)는 lean 정책상 이 도구가 없으므로, **dev 타겟**으로 워커를 빌드해야
> 동작합니다:
> ```bash
> docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build worker
> ```

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
| **행동 지침** | [`CLAUDE.md`](CLAUDE.md) | 9개 핵심 원칙 (아래 [개발 원칙](#개발-원칙)) |
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
| Qdrant | 6333 | 내부 전용, vault 의미 검색 벡터 DB |
| pocsandbox | 8770 | `--profile poc`, PoC 격리 실행 사이드카 (docker.sock 격리) |
| Postgres | 5432 | `--profile postgres`, 내부 전용 (DB_BACKEND=postgres 시) |
| vLLM | 8000 | `--profile vllm`, GPU 필요 |
| Prometheus | 9090 | `--profile monitoring` |
| Grafana | 3000 | `--profile monitoring` |
| cAdvisor / node-exporter | 내부 | `--profile monitoring`, Prometheus 수집 타깃 |

> Grafana 는 대시보드 3종(개요·시스템·작업로그)과 **알림 룰**(워커 실패·큐 적체·호스트 CPU)을 프로비저닝합니다.
> **Telegram 전송**은 Grafana 11 의 provisioning 이 contact point 의 `chatid` 를 숫자로 잘못 처리하는 이슈가 있어, **UI 에서 1회 설정**합니다:
> **Alerting → Contact points → Add** → type `Telegram`, 봇 토큰·chat id 입력 → **Notification policies** 의 기본 정책 receiver 를 이 contact point 로 지정. 이후 프로비저닝된 룰이 Telegram 으로 발송됩니다.

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

### `blog.yml` — 기술 블로그 (GitHub Pages)

`vault/` 는 비공개(gitignore)이므로, `scripts/publish_vault.py` 가 **`publish: true`** 인 노트만 git 추적 `site/content/` 로 export → push 시 Quartz 가 빌드해 GitHub Pages 에 발행합니다(카테고리=폴더, 계층 태그=태그 페이지). 미발행 노트는 git 에 올라가지 않습니다. 발행 표시는 로컬에서 `publish: true` 추가하거나 Telegram `/notes` 로 토글 후 `🚀 발행 적용`(export+push 자동)할 수 있습니다. 최초 1회 **Settings → Pages → Source = GitHub Actions** 설정 필요. 상세는 [`site/README.md`](site/README.md).

### `eval.yml` — 에이전트 품질 평가 (수동 + 야간)

`evals/` 는 멀티 에이전트 게이트웨이의 **라우팅·도구 계약·출력 품질**을 평가합니다(production 코드 무변경, 전부 monkeypatch).

- **결정론 회귀**(라우팅 일치·`must_call`/`forbidden` 도구 계약) — cassette 재생으로 **실 LLM 호출 0**. 일반 CI 의 [`tests/eval/`](tests/eval/) 에서 무과금으로 자동 검증.
- **품질 채점**(LLM-judge, 0~5) — 실 LLM 호출이라 과금. `eval.yml`(수동/야간)에서만. `CLAUDE_API_KEY` secret 필요.

```bash
uv run python -m evals --mode replay              # 결정론(무과금)
uv run python -m evals --mode live --out r.md     # 품질 채점(과금)
```

시나리오는 [`evals/scenarios/*.json`](evals/scenarios/) (입력 + 기대 route·도구 + judge 루브릭 + cassette).

---

## 개발 원칙

[`CLAUDE.md`](CLAUDE.md) 의 9개 원칙이 작업 방식을 규율합니다.

1. **Think Before Coding** — 가정을 명시하고, 모호하면 먼저 질문.
2. **Simplicity First** — 문제를 푸는 최소 코드. 투기적 추상화 금지.
3. **Surgical Changes** — 요청과 무관한 인접 코드를 "개선"하지 않음.
4. **Goal-Driven Execution** — 검증 가능한 완료 기준을 세우고 루프.
5. **Language** — 내부 추론은 영어, 응답은 한국어.
6. **Scope Clarification** — 파일 3개+·새 의존성·모호한 요구는 착수 전 확인.
7. **Plan Mode** — 복잡한 변경은 계획 먼저.
8. **Extended Guidelines** — `.claude/rules/` 가 위 원칙을 확장.
9. **Work Division & Workflow Routing** — 봇/워커는 코드 비변경(문서·`prompts/output/` 산출만), 코드 적용은 로컬 에이전트. 가벼운 작업은 CLAUDE.md 원칙대로 비례 적용, 중대 변경은 `prompts/01~06.md` 6단계를 표준으로.

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
| `VAULT_SUBDIR` | | `vault` | Obsidian 노트 저장 폴더 (WORKSPACE 기준) |
| `VAULT_INDEX_ENABLED` | | `true` | vault 벡터 인덱스(의미 검색) 사용 |
| `QDRANT_URL` | | `http://qdrant:6333` | Qdrant 주소 (내부 네트워크) |
| `EMBED_MODEL` | | `…multilingual-MiniLM-L12-v2` | fastembed ONNX 임베딩 모델 (다국어) |
| `EMBED_THREADS` | | `1` | onnxruntime 스레드 수 (메모리 절감) |
| `DIGEST_ENABLED` | | `false` | 정기 주간 브리핑 노트 자동 생성 (opt-in) |
| `DIGEST_INTERVAL_DAYS` | | `7` | 다이제스트 생성 주기(일) |
| `BRAVE_API_KEY` | | — | RAG 웹 검색용 |
| `WORKER_MODEL` | | `claude-sonnet-4-6` | 워커 Claude 모델 |
| `WORKER_MAX_TOKENS` | | `8192` | 최대 토큰 |
| `WORKER_MAX_ITERATIONS` | | `10` | ReAct 최대 반복 |
| `WORKER_TIMEOUT_S` | | `120` | 작업 타임아웃(초) |
| `POC_AUTOPILOT_MAX_ITERATIONS` | | `3` | `/pocrun` autopilot 빌드↔수정 최대 반복 |
| `VLLM_ENDPOINT` | | — | 설정 시 Claude 대신 vLLM 사용 |
| `VLLM_MODEL` | | `Qwen/Qwen2.5-Coder-7B-Instruct` | vLLM 서빙 모델 |
| `APP_IMAGE` | | `ghcr.io/currentjob/devops-pipeline:latest` | 레지스트리 실행 시 이미지 |
| `GRAFANA_ADMIN_PASSWORD` | monitoring 시 ✅ | — | Grafana 관리자 비밀번호 (미설정 시 기동 실패) |
| `POSTGRES_PASSWORD` | postgres 시 ✅ | — | Postgres 비밀번호 (미설정 시 기동 실패) |

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
