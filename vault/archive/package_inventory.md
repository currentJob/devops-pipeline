---
title: "설치된 패키지 목록 (Package Inventory)"
date: 2026-06-02
tags: [migrated]
source: migrated
---

# 설치된 패키지 목록 (Package Inventory)

> 기준일: 2026-06-02  
> 소스: `pyproject.toml` (직접 의존성) + `uv.lock` (전이 의존성)  
> Python 버전: >=3.12 (`requires-python = ">=3.12"`)  
> 패키지 매니저: **uv**

---

## 1. 직접 의존성 (pyproject.toml)

### 1-1. 프로덕션 의존성 (`[project.dependencies]`)

| 패키지 | 지정 버전 | 실제 설치 버전 | 역할 |
|--------|-----------|---------------|------|
| `anthropic` | >=0.102.0 | **0.102.0** | Claude API 클라이언트 |
| `python-dotenv` | >=1.2.2 | **1.2.2** | `.env` 환경변수 로드 |
| `python-telegram-bot` | >=22.7 | **22.7** | Telegram Bot 인터페이스 |
| `psutil` | >=6.0.0 | **7.2.2** | 시스템/프로세스 모니터링 |
| `aiohttp` | >=3.13.5 | **3.13.5** | 비동기 HTTP 클라이언트·서버 |
| `langchain-anthropic` | >=0.3.0 | **1.4.3** | LangChain × Claude 연동 |
| `langchain-core` | >=0.3.0 | **1.4.0** | LangChain 핵심 추상화 |
| `langchain-openai` | >=0.3.0 | **1.2.2** | LangChain × OpenAI/vLLM 연동 |
| `langgraph` | >=0.3.0 | **1.2.2** | 멀티 에이전트 그래프 실행 엔진 |
| `prometheus-client` | >=0.25.0 | **0.25.0** | Prometheus 메트릭 노출 |

### 1-2. 개발 의존성 (`[dependency-groups] dev`)

| 패키지 | 지정 버전 | 실제 설치 버전 | 역할 |
|--------|-----------|---------------|------|
| `pytest` | >=9.0.3 | **9.0.3** | 테스트 프레임워크 |
| `pytest-asyncio` | >=0.24.0 | **1.3.0** | asyncio 테스트 지원 |
| `ruff` | >=0.14.0 | **0.15.13** | 린터 + 포매터 (Rust 기반) |
| `pip-audit` | >=2.7.0 | **2.10.0** | CVE 취약점 감사 |
| `pre-commit` | >=4.0.0 | **4.6.0** | Git 훅 자동화 |

---

## 2. 전이 의존성 (uv.lock — 자동 해석)

아래는 `uv.lock`에서 확인된 모든 전이 의존성 패키지 목록입니다.

### 2-1. LangChain / LangGraph 생태계

| 패키지 | 버전 | 의존 대상 |
|--------|------|-----------|
| `langchain-protocol` | 0.0.15 | `langchain-core` |
| `langchain-core` | 1.4.0 | `langchain-anthropic`, `langchain-openai`, `langgraph` |
| `langgraph-checkpoint` | 4.1.1 | `langgraph` |
| `langgraph-prebuilt` | 1.1.0 | `langgraph` |
| `langgraph-sdk` | 0.3.15 | `langgraph` |
| `langsmith` | 0.8.6 | `langchain-core` |
| `jsonpatch` | 1.33 | `langchain-core` |
| `jsonpointer` | 3.1.1 | `jsonpatch` |
| `tenacity` | 9.1.4 | `langchain-core` |
| `uuid-utils` | 0.16.0 | `langchain-core`, `langsmith` |
| `xxhash` | 3.7.0 | `langgraph`, `langsmith` |

### 2-2. HTTP / 비동기 네트워크

| 패키지 | 버전 | 의존 대상 |
|--------|------|-----------|
| `httpx` | 0.28.1 | `anthropic`, `openai`, `python-telegram-bot`, `langsmith`, `langgraph-sdk` |
| `httpcore` | 1.0.9 | `httpx`, `python-telegram-bot` |
| `h11` | 0.16.0 | `httpcore` |
| `aiohappyeyeballs` | 2.6.1 | `aiohttp` |
| `aiosignal` | 1.4.0 | `aiohttp` |
| `frozenlist` | 1.8.0 | `aiohttp`, `aiosignal` |
| `multidict` | 6.7.1 | `aiohttp`, `yarl` |
| `yarl` | 1.23.0 | `aiohttp` |
| `propcache` | 0.5.2 | `yarl`, `aiohttp` |
| `attrs` | 26.1.0 | `aiohttp` |
| `websockets` | 16.0 | `langsmith` |

### 2-3. AI / ML 핵심

| 패키지 | 버전 | 의존 대상 |
|--------|------|-----------|
| `openai` | 2.38.0 | `langchain-openai` |
| `tiktoken` | 0.13.0 | `langchain-openai` |
| `jiter` | 0.14.0 | `anthropic`, `openai` |
| `orjson` | 3.11.9 | `langsmith`, `langgraph-sdk` |
| `ormsgpack` | 1.12.2 | `langgraph-checkpoint` |

### 2-4. 데이터 검증 / 직렬화

| 패키지 | 버전 | 의존 대상 |
|--------|------|-----------|
| `pydantic` | 2.13.4 | `anthropic`, `openai`, `langchain-*`, `langgraph` |
| `pydantic-core` | 2.46.4 | `pydantic` |
| `annotated-types` | 0.7.0 | `pydantic` |
| `typing-extensions` | 4.15.0 | 다수 |
| `typing-inspection` | 0.4.2 | `pydantic` |

### 2-5. HTTP 유틸리티 / 보안

| 패키지 | 버전 | 의존 대상 |
|--------|------|-----------|
| `certifi` | 2026.4.22 | `httpx`, `httpcore`, `requests` |
| `idna` | 3.15 | `httpx`, `yarl`, `anyio` |
| `charset-normalizer` | 3.4.7 | `requests` |
| `urllib3` | 2.7.0 | `requests` |
| `requests` | 2.34.2 | `langsmith`, `tiktoken`, `pip-audit` |
| `requests-toolbelt` | 1.0.0 | `langsmith` |
| `anyio` | 4.13.0 | `anthropic`, `openai`, `httpx` |
| `sniffio` | 1.3.1 | `anthropic`, `openai`, `anyio` |
| `distro` | 1.9.0 | `anthropic`, `openai` |

### 2-6. 직렬화 / 파싱

| 패키지 | 버전 | 의존 대상 |
|--------|------|-----------|
| `pyyaml` | 6.0.3 | `langchain-core`, `pre-commit` |
| `regex` | 2026.5.9 | `tiktoken` |
| `packaging` | 26.2 | `langchain-core`, `pytest`, `langsmith`, `pip-audit` |
| `msgpack` | 1.1.2 | `cachecontrol` |
| `docstring-parser` | 0.18.0 | `anthropic` |
| `zstandard` | 0.25.0 | `langsmith` |

### 2-7. 테스트 도구 (dev)

| 패키지 | 버전 | 의존 대상 |
|--------|------|-----------|
| `iniconfig` | 2.3.0 | `pytest` |
| `pluggy` | 1.6.0 | `pytest` |
| `pygments` | 2.20.0 | `pytest`, `rich` |
| `colorama` | 0.4.6 | `pytest` (Windows) |

### 2-8. pip-audit 전이 의존성 (dev)

| 패키지 | 버전 | 의존 대상 |
|--------|------|-----------|
| `pip-audit` | 2.10.0 | 직접 의존성 |
| `pip-api` | 0.0.34 | `pip-audit` |
| `pip-requirements-parser` | 32.0.1 | `pip-audit` |
| `cyclonedx-python-lib` | 11.7.0 | `pip-audit` |
| `cachecontrol[filecache]` | 0.14.4 | `pip-audit` |
| `filelock` | 3.29.0 | `cachecontrol`, `virtualenv` |
| `rich` | 15.0.0 | `pip-audit` |
| `markdown-it-py` | 4.2.0 | `rich` |
| `mdurl` | 0.1.2 | `markdown-it-py` |
| `tomli` | 2.4.1 | `pip-audit` |
| `tomli-w` | 1.2.0 | `pip-audit` |
| `pyparsing` | 3.3.2 | `pip-requirements-parser` |
| `license-expression` | 30.4.4 | `cyclonedx-python-lib` |
| `boolean-py` | 5.0 | `license-expression` |
| `packageurl-python` | 0.17.6 | `cyclonedx-python-lib` |
| `py-serializable` | 2.1.0 | `cyclonedx-python-lib` |
| `defusedxml` | 0.7.1 | `py-serializable` |
| `sortedcontainers` | 2.4.0 | `cyclonedx-python-lib` |
| `pip` | 26.1.1 | `pip-api` |
| `platformdirs` | 4.9.6 | `pip-audit`, `virtualenv` |

### 2-9. pre-commit 전이 의존성 (dev)

| 패키지 | 버전 | 의존 대상 |
|--------|------|-----------|
| `pre-commit` | 4.6.0 | 직접 의존성 |
| `cfgv` | 3.5.0 | `pre-commit` |
| `identify` | 2.6.19 | `pre-commit` |
| `nodeenv` | 1.10.0 | `pre-commit` |
| `virtualenv` | 21.3.3 | `pre-commit` |
| `distlib` | 0.4.0 | `virtualenv` |
| `python-discovery` | 1.3.1 | `virtualenv` |

### 2-10. Prometheus 클라이언트

| 패키지 | 버전 | 비고 |
|--------|------|------|
| `prometheus-client` | 0.25.0 | 직접 의존성, 전이 없음 |

---

## 3. 패키지 수 요약

| 구분 | 패키지 수 |
|------|-----------|
| 프로덕션 직접 의존성 | **10** |
| 개발 직접 의존성 | **5** |
| 전이 의존성 (lock 기준) | **약 70+** |
| **전체 합계 (uv.lock 기준)** | **약 85** |

---

## 4. 주요 버전 특이사항

| 항목 | 내용 |
|------|------|
| `langchain-core` 지정 vs 설치 | >=0.3.0 지정 → **1.4.0** 설치 (주 버전 차이 큼) |
| `langchain-anthropic` 지정 vs 설치 | >=0.3.0 지정 → **1.4.3** 설치 |
| `langchain-openai` 지정 vs 설치 | >=0.3.0 지정 → **1.2.2** 설치 |
| `langgraph` 지정 vs 설치 | >=0.3.0 지정 → **1.2.2** 설치 |
| `psutil` | >=6.0.0 지정 → **7.2.2** 설치 |
| `pytest-asyncio` | >=0.24.0 지정 → **1.3.0** 설치 |
| `anthropic` | >=0.102.0 지정 → **0.102.0** 설치 (최솟값) |
| `aiohttp` | >=3.13.5 지정 → **3.13.5** 설치 (최솟값) |
| `certifi` | **2026.4.22** — 최신 CA 번들 반영 |

---

> 생성: 2026-06-02 | 도구: uv.lock 파싱 + pyproject.toml 분석
