---
title: "DevOps 자동화 파이프라인 — 프로젝트 README"
date: 2026-06-01
tags: [migrated]
source: migrated
---

# DevOps 자동화 파이프라인 — 프로젝트 README

> 작성일: 2026-06-01 | 버전: 0.1.0

---

# DevOps 자동화 파이프라인

**Telegram 봇으로 제어하는 Claude AI 기반 DevOps 자동화 파이프라인입니다.**  
자연어 명령 한 줄로 코드 분석·품질 검사·Notion 리서치·서버 모니터링을 자동화합니다.

---

## 목차

1. [개요](#1-개요)
2. [아키텍처](#2-아키텍처)
3. [주요 기능](#3-주요-기능)
4. [기술 스택](#4-기술-스택)
5. [요구사항](#5-요구사항)
6. [빠른 시작](#6-빠른-시작)
7. [Telegram 명령어](#7-telegram-명령어)
8. [파이프라인 흐름](#8-파이프라인-흐름)
9. [환경변수 전체 목록](#9-환경변수-전체-목록)
10. [프로젝트 구조](#10-프로젝트-구조)
11. [개발 가이드](#11-개발-가이드)
12. [자동화 워크플로 프롬프트](#12-자동화-워크플로-프롬프트)
13. [보안 설계](#13-보안-설계)
14. [FAQ](#14-faq)

---

## 1. 개요

이 프로젝트는 **Telegram 봇을 컨트롤 타워**로 삼아, Claude AI 에이전트(Worker)가 실제 작업을 수행하는 2-서비스 아키텍처입니다.

- **Bot 서비스**: Telegram 메시지를 수신하고, 단순 명령은 직접 처리하며, 복잡한 자유형 작업은 Worker에 위임합니다.
- **Worker 서비스**: Claude tool-use 루프를 통해 bash 실행·파일 R/W·Notion API 등을 자율적으로 조합하여 작업을 완료합니다.

---

## 2. 아키텍처

```
[Telegram] ──명령──▶ [Bot 서비스 :8765]
                              │
                    작업 위임 (HTTP POST)
                              │
                              ▼
                      [Worker 서비스 :8766]
                              │
                    Claude tool-use 루프
                    (bash / 파일 / Notion)
                              │
                    결과 전송 (HTTP POST)
                              │
                              ▼
                      [Bot 서비스] ──응답──▶ [Telegram]
```

| 서비스 | 포트 | 역할 |
|--------|------|------|
| **Bot** | 8765 | Telegram 명령 수신 · 파이프라인 직접 실행 · Worker에 작업 위임 · 결과 알림 |
| **Worker** | 8766 | Claude tool-use 루프로 자유형 작업 처리 · bash / 파일 / Notion 도구 사용 |

### 컨테이너 구성

두 서비스는 Docker Compose의 **동일 내부 네트워크(`pipeline-net`)**에 위치하며, Worker는 호스트에 포트를 직접 노출하지 않습니다. Bot만 `127.0.0.1:8765`로 접근 가능합니다.

---

## 3. 주요 기능

| 기능 | 설명 |
|------|------|
| **파이프라인 실행** | 3단계(수집 → Claude 분석 → 실행) 자동화. 분석 후 Telegram으로 승인 요청, 승인 시 실행 |
| **자유형 작업 위임** | `/task <설명>`으로 자연어 작업을 Worker에 전달. Claude가 필요한 도구를 자율 선택 |
| **품질 검사** | `ruff` 린트 · `pytest` 테스트 · `pip-audit` CVE 보안 감사 |
| **서버 모니터링** | CPU / 메모리 / 디스크 현황 + Bot·Worker·Claude API 헬스체크 |
| **Notion 연동** | IT 트렌드 리서치 후 중복 확인을 거쳐 Notion 페이지 자동 생성 |
| **동시 작업 처리** | Worker 최대 3개 작업 동시 처리, 큐 최대 50개 |

---

## 4. 기술 스택

| 분류 | 도구 | 버전 |
|------|------|------|
| 언어 | Python | 3.12+ |
| 패키지 매니저 | uv | 최신 |
| AI | Anthropic Claude (claude-sonnet-4-6) | anthropic ≥ 0.102.0 |
| Telegram | python-telegram-bot | ≥ 22.7 |
| 에이전트 프레임워크 | LangChain / LangGraph | langchain-anthropic ≥ 0.3.0 |
| HTTP 클라이언트 | aiohttp | ≥ 3.13.5 |
| 시스템 모니터링 | psutil | ≥ 6.0.0 |
| 린터 | ruff | ≥ 0.14.0 |
| 테스트 | pytest + pytest-asyncio | ≥ 9.0.3 |
| 보안 감사 | pip-audit | ≥ 2.7.0 |
| 컨테이너 | Docker + Docker Compose | — |

---

## 5. 요구사항

- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)** — 패키지·가상환경 관리
- **Docker + Docker Compose** — 컨테이너 실행 시 필요
- **Telegram Bot Token** 및 **Chat ID** — [BotFather](https://t.me/botfather)에서 발급
- **Anthropic API Key** — [console.anthropic.com](https://console.anthropic.com)에서 발급
- (선택) **Notion Integration Token** + **Parent Page ID** — `/stack` 명령어 사용 시

---

## 6. 빠른 시작

### 6-1. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 값을 채웁니다:

```env
# ── 필수 ──────────────────────────────────────
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# ── AI (없으면 Claude 분석 기능 비활성화) ──────
CLAUDE_API_KEY=your_anthropic_api_key

# ── Notion (없으면 /stack 명령어 비활성화) ─────
NOTION_TOKEN=your_notion_integration_token
NOTION_PARENT_PAGE_ID=your_notion_page_id

# ── 기타 (기본값 사용 가능) ────────────────────
APPROVAL_TIMEOUT=300
LOG_LEVEL=INFO
```

### 6-2. Docker Compose로 실행 (권장)

```bash
# 빌드 및 실행
docker compose up --build

# 백그라운드 실행
docker compose up --build -d

# 로그 확인
docker compose logs -f
```

> **참고**: Bot은 Worker의 헬스체크가 통과된 이후에 기동됩니다(`depends_on: worker: condition: service_healthy`).

### 6-3. 로컬 실행 (개발용)

```bash
# 의존성 설치 (가상환경 자동 생성)
uv sync

# 봇 실행 (터미널 1)
uv run python -m app.main

# 워커 실행 (터미널 2)
uv run python -m app.worker.server
```

---

## 7. Telegram 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 봇 시작 및 주요 명령어 안내 |
| `/help` | 전체 명령어 목록 표시 |
| `/run` | 자동화 파이프라인 3단계 실행 |
| `/task <설명>` | 자유형 작업을 Worker에 위임 (예: `/task ruff 오류 수정해줘`) |
| `/status` | CPU / 메모리 / 디스크 서버 상태 조회 |
| `/uptime` | 봇 가동 시간 확인 |
| `/health` | Bot · Worker · Claude API 헬스체크 |
| `/lint` | `ruff check` 실행 후 결과 전송 |
| `/test` | `pytest` 실행 후 결과 전송 |
| `/audit` | `pip-audit` CVE 취약점 검사 |
| `/diff` | 마지막 커밋 변경 사항(`git diff HEAD~1`) 조회 |
| `/stack` | IT 트렌드 리서치 → Notion 페이지 자동 생성 |
| `/notion` | Notion 연결 상태 진단 |

---

## 8. 파이프라인 흐름

`/run` 명령 실행 시 아래 3단계가 순차 처리됩니다:

```
/run 입력
  │
  ├─▶ 1단계: 데이터 수집 (step_collect)
  │         └─ 프로젝트 상태·변경사항 등 컨텍스트 수집
  │
  ├─▶ 2단계: Claude 분석 (step_analyze)
  │         └─ 수집된 데이터를 Claude가 분석, 실행 계획 생성
  │         └─ Telegram으로 승인 요청 발송 (대기: APPROVAL_TIMEOUT초)
  │               ├─ ✅ 승인 → 3단계로 진행
  │               └─ ❌ 거절 → 파이프라인 중단
  │
  └─▶ 3단계: 실행 (step_execute)
            └─ 승인된 계획을 실제로 수행
```

> `app/pipeline.py`의 `step_collect`, `step_analyze`, `step_execute` 함수를 실제 업무 로직으로 교체하여 사용합니다.

---

## 9. 환경변수 전체 목록

| 변수 | 필수 | 기본값 | 설명 |
|------|:----:|--------|------|
| `TELEGRAM_TOKEN` | ✅ | — | Telegram Bot API 토큰 |
| `TELEGRAM_CHAT_ID` | ✅ | — | 허용할 Telegram Chat ID |
| `CLAUDE_API_KEY` | | — | Anthropic API 키 |
| `APPROVAL_TIMEOUT` | | `300` | 파이프라인 승인 대기 시간(초) |
| `LOG_LEVEL` | | `INFO` | 로그 레벨 (DEBUG / INFO / WARNING / ERROR) |
| `NOTION_TOKEN` | | — | Notion Integration 토큰 |
| `NOTION_PARENT_PAGE_ID` | | — | Notion 부모 페이지 ID |
| `BRAVE_API_KEY` | | — | Brave Search API 키 (웹 검색 기능) |
| `WORKER_MODEL` | | `claude-sonnet-4-6` | Worker에서 사용할 Claude 모델 |
| `WORKER_MAX_TOKENS` | | `8192` | Worker 최대 토큰 수 |
| `WORKER_MAX_ITERATIONS` | | `10` | tool-use 최대 반복 횟수 |
| `WORKER_TIMEOUT_S` | | `120` | Worker 작업 타임아웃(초) |
| `WORKER_MAX_CONCURRENT` | | `3` | 동시 처리 가능한 최대 작업 수 |
| `WORKER_QUEUE_SIZE` | | `50` | Worker 작업 큐 최대 크기 |
| `BOT_NOTIFY_URL` | | `http://bot:8765/notify` | Bot 알림 수신 엔드포인트 |
| `BOT_RESULT_URL` | | `http://bot:8765/worker-result` | Worker 결과 수신 엔드포인트 |
| `WORKER_URL` | | `http://worker:8766/run` | Worker 작업 실행 엔드포인트 |
| `WORKER_HEALTH_URL` | | `http://worker:8766/health` | Worker 헬스체크 엔드포인트 |
| `WORKER_TASKS_URL` | | `http://worker:8766/tasks` | Worker 작업 목록 조회 엔드포인트 |

---

## 10. 프로젝트 구조

```
devops-pipeline/
├── app/
│   ├── main.py              # 봇 진입점: Telegram Application 초기화·기동
│   ├── config.py            # 환경변수 로드 및 검증 (필수값 누락 시 즉시 RuntimeError)
│   ├── bot/
│   │   ├── commands.py      # Telegram 명령어 핸들러 등록
│   │   ├── notifier.py      # Telegram 메시지 발송·수신 헬퍼
│   │   └── server.py        # Bot HTTP 서버 (:8765) — Worker 결과 수신
│   ├── pipeline.py          # 파이프라인 3단계 로직 (커스터마이즈 대상)
│   └── worker/
│       └── server.py        # Worker HTTP 서버 (:8766) + Claude tool-use 루프
├── prompts/
│   ├── 00_README.md         # 자동화 워크플로 전체 인덱스
│   ├── 01_analyze.md        # 단계 1: 프로젝트 진단
│   ├── 02_research.md       # 단계 2: 2026 트렌드 리서치
│   ├── 03_design.md         # 단계 3: 아키텍처 설계 (인간 게이트)
│   ├── 04_implement.md      # 단계 4: 외과적 구현
│   ├── 05_review.md         # 단계 5: 코드 품질 검수 (인간 게이트)
│   ├── 06_test.md           # 단계 6: 자동 테스트·릴리스 게이트
│   └── output/              # 각 단계 산출물 저장 디렉토리
├── tests/                   # pytest 테스트 스위트
├── logs/                    # 런타임 로그 (볼륨 마운트)
├── data/                    # Worker 작업 데이터 (볼륨 마운트)
├── Dockerfile               # 멀티 스테이지 빌드 (builder → runtime)
├── docker-compose.yml       # Bot + Worker 서비스 정의
├── pyproject.toml           # 프로젝트 메타데이터·의존성·도구 설정
├── CLAUDE.md                # AI 행동 지침 (추측 금지·외과적 변경·한국어 응답)
└── .env.example             # 환경변수 템플릿
```

---

## 11. 개발 가이드

### 테스트 실행

```bash
# 전체 테스트
uv run pytest tests/ -v

# 특정 파일
uv run pytest tests/test_pipeline.py -v

# 커버리지 포함
uv run pytest tests/ --cov=app --cov-report=term-missing
```

### 코드 품질

```bash
# 린트 검사
uv run ruff check .

# 린트 자동 수정
uv run ruff check . --fix

# 포매터
uv run ruff format .
```

### 보안 감사

```bash
# CVE 취약점 검사
uv run pip-audit
```

### pre-commit 훅

```bash
# 훅 설치 (최초 1회)
uv run pre-commit install

# 수동 실행
uv run pre-commit run --all-files
```

### 의존성 추가

```bash
# 운영 의존성
uv add <패키지명>

# 개발 의존성
uv add --dev <패키지명>
```

---

## 12. 자동화 워크플로 프롬프트

`prompts/` 디렉토리에는 Claude 에이전트에게 순서대로 주입하는 **6단계 워크플로 프롬프트**가 있습니다.

| 단계 | 파일 | 역할 | 게이트 |
|------|------|------|--------|
| 01 | `01_analyze.md` | 프로젝트 진단·인벤토리 | 자동 진행 |
| 02 | `02_research.md` | 2026 DevOps 트렌드 리서치 | 자동 진행 |
| 03 | `03_design.md` | 아키텍처 설계·대안 비교 | ⏸️ **사람 승인 필수** |
| 04 | `04_implement.md` | 외과적 코드 구현 | 자체 검증 |
| 05 | `05_review.md` | 코드 품질 검수 | ⏸️ **사람 승인 필수** |
| 06 | `06_test.md` | 자동 테스트·릴리스 게이트 | 🚦 릴리스 게이트 |

각 단계의 산출물은 `prompts/output/` 에 저장되며, 다음 단계의 입력으로 연결됩니다.

---

## 13. 보안 설계

### 컨테이너 하드닝

- **멀티 스테이지 빌드**: `builder` → `runtime` 분리로 빌드 도구 미포함
- **Non-root 실행**: `appuser` 전용 유저 생성 후 실행
- **읽기 전용 파일시스템**: `read_only: true` + 필요 경로만 `tmpfs`/볼륨 마운트
- **권한 상승 차단**: `no-new-privileges: true`
- **포트 최소화**: Worker는 내부 네트워크만 사용, Bot은 `127.0.0.1`만 바인딩

### 접근 제어

- Telegram Chat ID 화이트리스트로 허가된 사용자만 명령 가능
- 환경변수 미설정 시 관련 기능 자동 비활성화 (Notion, Claude 등)

### 의존성 보안

- `pip-audit`로 CVE 정기 감사 (`/audit` 명령어 또는 CI에서 실행)
- `ruff`의 `B` (bugbear), `UP` (pyupgrade) 룰셋으로 코드 품질 유지

---

## 14. FAQ

**Q. 1인 운영 프로젝트인데 아키텍처가 복잡하지 않나요?**  
A. Bot과 Worker를 분리한 이유는 **Claude tool-use 루프의 실행 시간이 길어질 수 있기 때문**입니다. Bot이 Telegram 응답성을 유지하면서 Worker가 독립적으로 장시간 작업을 처리할 수 있습니다.

**Q. CLAUDE_API_KEY 없이도 동작하나요?**  
A. 네. API 키 없이도 `/status`, `/health`, `/lint`, `/test`, `/audit`, `/diff` 등 대부분의 명령어가 동작합니다. Claude 분석이 필요한 `/run` 파이프라인과 `/task`만 비활성화됩니다.

**Q. Worker 모델을 바꾸고 싶습니다.**  
A. `.env`의 `WORKER_MODEL` 값을 변경하세요. Anthropic에서 지원하는 모든 모델 ID를 사용할 수 있습니다.

**Q. `/task`로 어떤 작업을 시킬 수 있나요?**  
A. bash 명령 실행, 파일 읽기/쓰기, Notion 페이지 생성 등 Worker에 등록된 도구 범위 내의 모든 자연어 작업을 처리할 수 있습니다. 예: `/task 최근 로그에서 ERROR 건수 세어줘`, `/task pytest 실패 원인 분석해줘`.

**Q. 승인 타임아웃(APPROVAL_TIMEOUT)이 지나면 어떻게 되나요?**  
A. 파이프라인이 자동으로 중단되고, Telegram으로 타임아웃 알림이 발송됩니다. 기본값은 300초(5분)입니다.

---

*이 문서는 2026-06-01 기준으로 작성되었습니다.*
