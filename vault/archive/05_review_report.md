---
title: "05 검수 + 06 테스트 통합 보고서 — 사이클 10 (/stack + Notion 통합)"
date: 2026-05-22
tags: [migrated]
source: migrated
---

# 05 검수 + 06 테스트 통합 보고서 — 사이클 10 (/stack + Notion 통합)

## 0. 변경 요약

| 파일 | 변경 | LoC |
|---|---|---|
| `app/notion_client.py` | 신규 — Notion REST API 클라이언트 + 마크다운 → 블록 파서 | ~125 |
| `app/tools.py` | `notion_search`, `notion_create_page` 도구 추가 + execute 디스패치 확장 | +60 |
| `app/config.py` | NOTION_TOKEN, NOTION_PARENT_PAGE_ID 추가 | +3 |
| `app/commands.py` | `cmd_stack` 핸들러 + help 메시지 + 등록 | +50 |
| `app/worker.py` | system prompt 에 새 도구 + [STACK_TASK] 가이드 | +6 |
| `.env.example` | NOTION_TOKEN, NOTION_PARENT_PAGE_ID 안내 | +6 |
| `tests/unit/test_notion_client.py` | 신규 — 8개 파서 테스트 | ~75 |
| **합계** | | **~325 LoC** |

설계 예상치 340 LoC 와 거의 일치.

## 1. /stack 워크플로 흐름

```
사용자  /stack  ──▶  봇 cmd_stack
                       ↓ _dispatch_to_worker (description = [STACK_TASK] ...)
                  워커 _process_task
                       ↓ Claude tool use 루프 (최대 10회)
                       ├─ notion_search("IT 트렌드")        ──▶ Notion API
                       ├─ notion_search("tech stack")
                       ├─ notion_search("학습 로드맵")
                       ├─ notion_search("technology")
                       ↓ 결과 분석 → 중복되지 않는 카테고리 3~5개 선정
                       ↓ Claude 가 자체 지식으로 마크다운 작성
                       └─ notion_create_page(title, content, "🆕") ──▶ Notion API
                       ↓ URL 추출
                  봇 worker-result 엔드포인트
                       ↓ Telegram send_message
                  사용자 텔레그램 도착
```

## 2. 보안·신뢰성

| 항목 | 처리 |
|---|---|
| NOTION_TOKEN 미설정 | `_notion_search` / `_notion_create_page` 에서 "거부" 응답. 흐름 자체는 깨지지 않음 (Claude 가 사용자에게 안내) |
| NOTION_PARENT_PAGE_ID 미설정 | 생성 단계에서만 거부. 검색은 가능 |
| 외부 API 실패 (4xx/5xx) | RuntimeError 또는 error dict 반환. 도구 결과로 Claude 가 인식, 다시 시도 또는 종료 |
| Rich text 길이 한도 | Notion 의 2000자/블록 한도를 `_rich_text` 가 자동 청킹 |
| children 블록 100개 한도 | `markdown_to_blocks` 가 100개로 자동 절단 |
| 권한 검증 | `cmd_stack` 도 `_authorized()` 게이트 적용 |
| 시크릿 노출 | NOTION_TOKEN 은 .env 에만, 코드에 하드코딩 0 |

## 3. 차원별 검수

| 차원 | 판정 | 근거 |
|---|---|---|
| A. 설계 일치성 | 🟢 | "제목+요약 기반 중복 회피" 결정 그대로 — notion_search 결과의 제목을 Claude 가 분석 |
| B. 외과적 변경 | 🟢 | 신규 파일 2개 + 기존 4개 파일 추가만. `app/pipeline.py`, `app/notifier.py`, `app/notify_http.py`, `app/main.py` 무변경 |
| C. 보안 | 🟢 | 권한 게이트 유지. Notion API 외부 호출은 aiohttp + 명시적 토큰. SSL 검증 기본값 사용 |
| D. 신뢰성 | 🟢 | 누락 환경 변수에 명확한 에러. 외부 API 실패는 Claude tool result 로 전달되어 처리 가능 |
| E. 가독성 | 🟢 | notion_client 가 독립 모듈. tools.py 의 디스패치는 일관된 패턴 |
| F. 테스트 | 🟡 | 파서 8개 단위 테스트 작성. HTTP 호출은 통합 테스트 (사용자 머신 e2e) |
| G. 운영성 | 🟢 | 환경 변수 명세가 `.env.example` 에 문서화. 통합 공유 단계 안내 포함 |

## 4. 사용자 머신 실행 체크리스트

### A. 사전 설정 — Notion 통합 발급
1. https://www.notion.so/profile/integrations 접속
2. "New integration" 생성 (이름: 예 `devops-pipeline-worker`, 타입: Internal)
3. 생성된 **Internal Integration Token** 복사
4. Notion 에서 **부모 페이지** 결정 (예: 새 페이지 "IT Stack Hub" 생성)
5. 그 페이지의 우측 상단 `⋯` → "Connections" → 위 통합 추가
6. 페이지 URL 의 마지막 32자 hex 가 페이지 ID (예: `https://www.notion.so/abc123def...` → `abc123def...`)

### B. `.env` 갱신
```
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxx
NOTION_PARENT_PAGE_ID=abc123def...
```

### C. 회귀 + 신규 테스트
```powershell
cd D:\devops-pipeline
uv run ruff check --fix .
uv run ruff format .
uv run pytest tests/unit/ -v   # 25 + 8 = 33개 통과 기대
```

### D. 컨테이너 재빌드 (봇·워커 모두)
```powershell
docker compose down
docker compose up -d --build
docker compose logs worker --tail=20
docker compose logs bot --tail=20
```

### E. 텔레그램에서 검증
1. `/help` → `/stack` 항목이 "트렌드 리서치" 카테고리에 표시되는지
2. `/health` → bot 🟢 / worker 🟢 / Claude API 🟢 (NOTION 은 health 항목 없음 — 추후 추가 가능)
3. `/stack` 명령 실행
   - 즉시: `🚀 작업 시작 (id=xxxxxxxx)`
   - **30초~2분 후**: `✅ 작업 완료 (id=xxxxxxxx)` + Notion 페이지 URL
4. 페이지를 Notion 에서 열어 확인:
   - 제목이 "2026 신규 트렌드 — YYYY-MM-DD"
   - 본문이 3~5개 카테고리, 각각 4섹션 구조
   - 이전 페이지에 있던 카테고리(AI 에이전트, WebAssembly 등)와 중복 최소
   - 아이콘 🆕

### F. 실패 시나리오 검증 (선택)
NOTION_TOKEN 을 일시 제거 후 `/stack` → Claude 가 "NOTION_TOKEN 미설정" 도구 결과를 받고 사용자에게 안내 메시지로 응답.

### G. 사이클 10 완료 알림
```powershell
uv run python -m tools.notify "🆕 *사이클10 완료* /stack 명령어 + Notion 통합 도입. 봇이 12개 명령어 지원. 트렌드 조사→중복 회피→Notion 자동 게시 파이프라인 구축."
```

## 5. 알려진 제약 + 후속 작업

| # | 항목 | 사이클 |
|---|---|---|
| 1 | § 4 A~E 실행 + Notion 페이지 도착 확인 | 본 사이클 종료 조건 |
| 2 | 중복 회피 정밀도 향상 — 페이지 본문 fetch 후 내용 비교 (현재는 제목만) | 11 |
| 3 | `/stack <영역>` — 사용자가 영역 지정 (예: `/stack 데이터`) | 11 |
| 4 | 페이지 생성 후 텔레그램에 페이지 미리보기 (제목 + 카테고리 목록) | 11 |
| 5 | `/health` 에 NOTION 상태 추가 | 11 |
| 6 | 마크다운 inline 포맷 (링크, 굵게, 코드) 블록 변환 | 12 |
| 7 | 누적된 5+ 사이클의 검증 미실행 백로그 (사이클 7-9 의 e2e) | 12 |

## 6. 결론

> 🟡 **조건부 통과**: 정적 검증 + 단위 테스트 33개(예상). § 4 의 Notion 통합 발급 → e2e 까지 통과 시 사이클 10 릴리스 가능.
