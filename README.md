# DevOps 자동화 파이프라인

Telegram 봇으로 제어하는 Claude AI 기반 DevOps 자동화 파이프라인입니다.  
봇에서 명령을 받아 워커가 Claude tool-use 루프로 작업을 처리하고, 결과를 Telegram으로 알립니다.

## 아키텍처

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

| 서비스 | 역할 |
|--------|------|
| **Bot** | Telegram 명령 수신 · 파이프라인 직접 실행 · 워커에 작업 위임 |
| **Worker** | Claude tool-use 루프로 자유형 작업 처리 · bash / 파일 / Notion 도구 사용 |

## 주요 기능

- **파이프라인 실행**: 3단계(수집 → Claude 분석 → 실행) 자동화, 중간에 Telegram 승인 요청
- **자유형 작업 위임**: `/task <설명>`으로 워커에 자연어 작업 전달
- **품질 검사**: lint(ruff) · 테스트(pytest) · 보안 감사(pip-audit)
- **서버 모니터링**: CPU / 메모리 / 디스크 · 봇+워커+Claude API 헬스체크
- **Notion 연동**: IT 트렌드 리서치 후 중복 회피하여 새 페이지 자동 생성

## 요구사항

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- Docker + Docker Compose (컨테이너 실행 시)
- Telegram Bot Token 및 Chat ID
- Anthropic API Key

## 빠른 시작

### 1. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 값을 채웁니다.

```env
# 필수
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# 선택 (없으면 Claude 분석 기능 비활성화)
CLAUDE_API_KEY=your_anthropic_api_key

# 선택 (없으면 /stack 명령어 비활성화)
NOTION_TOKEN=your_notion_integration_token
NOTION_PARENT_PAGE_ID=your_notion_page_id

# 기타 (기본값 사용 가능)
APPROVAL_TIMEOUT=300
LOG_LEVEL=INFO
```

### 2. Docker Compose로 실행

```bash
docker compose up --build
```

### 3. 로컬 실행 (개발용)

```bash
# 의존성 설치
uv sync

# 봇 실행
uv run python -m app.main

# 워커 실행 (별도 터미널)
uv run python -m app.worker
```

## Telegram 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 봇 시작 및 주요 명령어 안내 |
| `/help` | 전체 명령어 목록 |
| `/run` | 자동화 파이프라인 실행 |
| `/task <설명>` | 자유형 작업 워커에 위임 |
| `/status` | CPU / 메모리 / 디스크 상태 |
| `/uptime` | 봇 가동 시간 |
| `/health` | 봇 · 워커 · Claude API 헬스체크 |
| `/lint` | ruff check 실행 |
| `/test` | pytest 실행 |
| `/audit` | pip-audit (CVE 검사) 실행 |
| `/diff` | 마지막 커밋 변경 사항 조회 |
| `/stack` | IT 트렌드 조사 → Notion 페이지 생성 |
| `/notion` | Notion 연결 상태 진단 |

## 파이프라인 흐름

```
/run 입력
  └─▶ 1단계: 데이터 수집
  └─▶ 2단계: Claude 분석 + Telegram 승인 요청
        ├─ 승인 → 3단계: 실행
        └─ 거절 → 파이프라인 중단
```

`app/pipeline.py`의 `step_collect`, `step_analyze`, `step_execute`를 실제 업무 로직으로 교체하여 사용합니다.

## 개발

```bash
# 테스트
uv run pytest tests/ -v

# 린트
uv run ruff check .

# 보안 감사
uv run pip-audit

# pre-commit 훅 설치
uv run pre-commit install
```

## 환경변수 전체 목록

| 변수 | 필수 | 기본값 | 설명 |
|------|:----:|--------|------|
| `TELEGRAM_TOKEN` | ✅ | — | Telegram Bot API 토큰 |
| `TELEGRAM_CHAT_ID` | ✅ | — | 허용할 Telegram Chat ID |
| `CLAUDE_API_KEY` | | — | Anthropic API 키 |
| `APPROVAL_TIMEOUT` | | `300` | 승인 대기 시간(초) |
| `LOG_LEVEL` | | `INFO` | 로그 레벨 |
| `NOTION_TOKEN` | | — | Notion Integration 토큰 |
| `NOTION_PARENT_PAGE_ID` | | — | Notion 부모 페이지 ID |
| `WORKER_PORT` | | `8766` | 워커 HTTP 포트 |
| `WORKER_MODEL` | | `claude-haiku-4-5-20251001` | 워커에서 사용할 Claude 모델 |
| `WORKER_MAX_TOKENS` | | `8192` | 워커 최대 토큰 |
| `WORKER_MAX_ITERATIONS` | | `10` | tool-use 최대 반복 횟수 |
| `WORKER_TIMEOUT_S` | | `120` | 워커 작업 타임아웃(초) |
