---
title: "설치된 패키지 목록 (2026-06-02)"
date: 2026-06-02
tags: [migrated]
source: migrated
---

# 설치된 패키지 목록 (2026-06-02)

> 출처: `pyproject.toml` + `uv.lock` (revision 3)
> Python 요구 버전: `>=3.12`

---

## 1. 프로덕션 의존성 (dependencies)

| # | 패키지 | 지정 버전 범위 | Lock 버전 | 분류 |
|---|--------|--------------|-----------|------|
| 1 | `anthropic` | `>=0.102.0` | 0.102.0 | AI / LLM SDK |
| 2 | `python-dotenv` | `>=1.2.2` | 1.2.2 | 환경변수 관리 |
| 3 | `python-telegram-bot` | `>=22.7` | 22.7 | Telegram 봇 |
| 4 | `psutil` | `>=6.0.0` | 6.0.0 | 시스템 모니터링 |
| 5 | `aiohttp` | `>=3.13.5` | 3.13.5 | 비동기 HTTP 클라이언트 |
| 6 | `langchain-anthropic` | `>=0.3.0` | 0.3.x | LangChain / Anthropic |
| 7 | `langchain-core` | `>=0.3.0` | 0.3.x | LangChain 핵심 |
| 8 | `langchain-openai` | `>=0.3.0` | 0.3.x | LangChain / OpenAI |
| 9 | `langgraph` | `>=0.3.0` | 0.3.x | LangGraph 워크플로우 |
| 10 | `prometheus-client` | `>=0.25.0` | 0.25.0 | 메트릭 수집 |

---

## 2. 개발 의존성 (dev dependency-group)

| # | 패키지 | 지정 버전 범위 | 분류 |
|---|--------|--------------|------|
| 1 | `pytest` | `>=9.0.3` | 테스트 프레임워크 |
| 2 | `pytest-asyncio` | `>=0.24.0` | 비동기 테스트 지원 |
| 3 | `ruff` | `>=0.14.0` | Linter / Formatter |
| 4 | `pip-audit` | `>=2.7.0` | 보안 취약점 감사 |
| 5 | `pre-commit` | `>=4.0.0` | Git hooks 관리 |

---

## 3. 전이 의존성 (Transitive Dependencies) — uv.lock 기준

아래는 `uv.lock`에 고정된 전이 의존성 패키지 목록입니다.

| # | 패키지 | Lock 버전 | 주요 역할 |
|---|--------|-----------|----------|
| 1 | `aiohappyeyeballs` | 2.6.1 | aiohttp 비동기 DNS 최적화 |
| 2 | `aiohttp` | 3.13.5 | 비동기 HTTP |
| 3 | `aiosignal` | (lock 포함) | aiohttp 시그널 처리 |
| 4 | `annotated-types` | (lock 포함) | 타입 어노테이션 확장 |
| 5 | `anthropic` | 0.102.0 | Anthropic API |
| 6 | `anyio` | (lock 포함) | 비동기 I/O 추상화 |
| 7 | `attrs` | (lock 포함) | 데이터 클래스 유틸 |
| 8 | `certifi` | (lock 포함) | TLS 인증서 |
| 9 | `charset-normalizer` | (lock 포함) | 문자 인코딩 감지 |
| 10 | `distlib` | (lock 포함) | 패키지 배포 유틸 |
| 11 | `distro` | (lock 포함) | OS 정보 |
| 12 | `filelock` | (lock 포함) | 파일 잠금 |
| 13 | `frozenlist` | (lock 포함) | 불변 리스트 (aiohttp) |
| 14 | `h11` | (lock 포함) | HTTP/1.1 파서 |
| 15 | `httpcore` | (lock 포함) | HTTP 코어 |
| 16 | `httpx` | (lock 포함) | 동기/비동기 HTTP 클라이언트 |
| 17 | `httpx-sse` | (lock 포함) | SSE 스트리밍 |
| 18 | `idna` | (lock 포함) | 국제 도메인명 |
| 19 | `jiter` | (lock 포함) | JSON 파서 (anthropic) |
| 20 | `jsonpatch` | (lock 포함) | JSON Patch |
| 21 | `jsonpointer` | (lock 포함) | JSON Pointer |
| 22 | `langchain-core` | 0.3.x | LangChain 핵심 |
| 23 | `langchain-anthropic` | 0.3.x | LangChain Anthropic |
| 24 | `langchain-openai` | 0.3.x | LangChain OpenAI |
| 25 | `langgraph` | 0.3.x | LangGraph |
| 26 | `langgraph-checkpoint` | (lock 포함) | LangGraph 체크포인트 |
| 27 | `langgraph-sdk` | (lock 포함) | LangGraph SDK |
| 28 | `msgspec` | (lock 포함) | 고속 직렬화 |
| 29 | `multidict` | (lock 포함) | 멀티 딕셔너리 (aiohttp) |
| 30 | `openai` | (lock 포함) | OpenAI API |
| 31 | `orjson` | (lock 포함) | 고속 JSON |
| 32 | `packaging` | (lock 포함) | 패키지 버전 유틸 |
| 33 | `platformdirs` | (lock 포함) | OS 플랫폼 경로 |
| 34 | `pre-commit` | 4.x | Git hook 관리 |
| 35 | `propcache` | (lock 포함) | 속성 캐싱 |
| 36 | `prometheus-client` | 0.25.0 | 메트릭 노출 |
| 37 | `psutil` | 6.0.0 | 시스템 리소스 |
| 38 | `pydantic` | (lock 포함) | 데이터 검증 |
| 39 | `pydantic-core` | (lock 포함) | Pydantic 핵심 |
| 40 | `pydantic-settings` | (lock 포함) | 설정 관리 |
| 41 | `python-dotenv` | 1.2.2 | .env 파일 로드 |
| 42 | `python-telegram-bot` | 22.7 | Telegram Bot API |
| 43 | `PyYAML` | (lock 포함) | YAML 파서 |
| 44 | `regex` | (lock 포함) | 정규식 확장 |
| 45 | `requests` | (lock 포함) | HTTP 요청 |
| 46 | `sniffio` | (lock 포함) | 비동기 라이브러리 감지 |
| 47 | `tenacity` | (lock 포함) | 재시도 유틸 |
| 48 | `tiktoken` | (lock 포함) | 토큰 카운터 (OpenAI) |
| 49 | `tqdm` | (lock 포함) | 진행바 |
| 50 | `typing-extensions` | (lock 포함) | 타입 힌트 확장 |
| 51 | `urllib3` | (lock 포함) | HTTP 클라이언트 |
| 52 | `virtualenv` | (lock 포함) | 가상환경 관리 |
| 53 | `yarl` | (lock 포함) | URL 파서 (aiohttp) |

---

## 4. 요약 통계

| 구분 | 수량 |
|------|------|
| 프로덕션 직접 의존성 | 10개 |
| 개발 직접 의존성 | 5개 |
| 전이 의존성 (추정) | 38개 이상 |
| **총계** | **53개 이상** |

---

## 5. 비고

- **uv** 버전 잠금 파일(`uv.lock`) revision 3 기준
- 전이 의존성 버전은 lock 파일에 고정되어 있으나, 일부는 플랫폼(OS/아키텍처)별 wheel 분기가 존재함
- 보안 감사가 필요한 경우 `uv run pip-audit` 명령 실행 권장
- dev 그룹 패키지는 프로덕션 빌드에 포함되지 않음 (Dockerfile 확인 권장)
