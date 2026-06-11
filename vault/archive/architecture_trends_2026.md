---
title: "🏗️ 최신 트렌드 코드 구조 분석 보고서"
date: 2026-06-02
tags: [migrated]
source: migrated
---

# 🏗️ 최신 트렌드 코드 구조 분석 보고서
> 분석 대상: 현재 프로젝트 전체 (`app/`)  
> 분석 일자: 2026-06-02  
> 분석 기준: 2025~2026 Python 백엔드 / AI 에이전트 아키텍처 트렌드

---

## 1. 전체 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                          사용자 (Telegram)                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │ /run /code /doc /plan …
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  🤖 Bot 서비스  (port 8765)                       │
│   app/main.py → app/bot/{server, commands, notifier}            │
│   • telegram-bot 수신 → 명령 파싱                                │
│   • POST /notify, /worker-result 수신 → Telegram 재전달          │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTP POST /run
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ⚙️ Worker 서비스  (port 8766)                    │
│   app/worker/{server, agent, store, metrics}                    │
│   • asyncio.Queue + Semaphore → 동시성 제어                      │
│   • SQLite(tasks.db) → 작업 이력                                 │
│   • Prometheus /metrics 노출                                     │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                    ┌───────────┼──────────────┐
                    ▼           ▼              ▼
          ┌──────────────┐  ┌────────┐  ┌──────────┐
          │  LangGraph   │  │  RAG   │  │ Pipeline │
          │  Multi-Agent │  │Retriev.│  │ runner   │
          └──────┬───────┘  └────────┘  └──────────┘
                 │
      ┌──────────┼──────────────────┐
      ▼          ▼                  ▼
  [Claude]   [vLLM]   Tools: bash / read_file / write_file
                              notion_search / notion_create_page
```

---

## 2. 채택된 최신 트렌드 패턴 (✅ 잘 된 점)

### 2-1. 멀티 에이전트 + LangGraph
```
START → retrieve → router → code|doc|infra|stack|general → END
```
- `Route(StrEnum)` 으로 타입 안전한 라우팅 정의  
- `_PREFIX_MAP` 을 이용한 **결정론적 라우팅** (LLM 판단 없이 prefix 로 즉시 분기)  
- LangGraph `StateGraph` + `create_react_agent` 조합 → **2025 AI 에이전트 표준 패턴**

### 2-2. Dual-Backend LLM Routing (Claude ↔ vLLM)
```python
# app/agent/graph.py
if await _vllm_available() and route in config.VLLM_ROUTES_SET:
    llm = _make_vllm_llm(...)   # 로컬 vLLM
else:
    llm = ChatAnthropic(...)     # Claude API 폴백
```
- 헬스 캐시(`_VLLM_HEALTH_TTL_S = 30s`) 로 불필요한 프로브 방지  
- 라우트별 백엔드 분리 → 비용 최적화 패턴

### 2-3. asyncio 기반 완전 비동기 설계
- `asyncio.Queue` + `asyncio.Semaphore` 로 워커 동시성 제어  
- `asyncio.to_thread()` 로 동기 Claude SDK 호출을 이벤트 루프 블로킹 없이 처리  
- `aiohttp.web` 경량 HTTP 서버 (Bot / Worker 각각 분리 포트)

### 2-4. Prometheus + Grafana 관측성
```python
# app/worker/metrics.py
TASKS_TOTAL    = Counter(...)
TASK_DURATION  = Histogram(...)
INFLIGHT       = Gauge(...)
QUEUE_SIZE     = Gauge(...)
```
- **RED 메트릭** (Rate / Error / Duration) 구조적으로 모두 커버  
- `track_inprogress()` context manager 로 예외 시에도 게이지 복구 보장

### 2-5. RAG (Retrieval-Augmented Generation)
- Brave Search API → 로컬 문서 2단 폴백 구조  
- 에이전트 `retrieve` 노드가 프롬프트 전에 자동 실행 → 최신 데이터 주입

### 2-6. SQLite 경량 영속성
- 추가 인프라(Redis/Postgres) 없이 `sqlite3` 단독 사용  
- `@contextmanager` 로 커넥션 라이프사이클 엄격 관리

---

## 3. 개선이 필요한 구조적 이슈

### 🔴 Issue 1: 전역 가변 상태 — `app/worker/server.py:25-26`
```python
# Before (안티패턴 — 모듈 레벨 가변 전역)
_queue: asyncio.Queue[_Job] = asyncio.Queue(maxsize=0)   # 실제 크기는 main()에서 교체
_semaphore: asyncio.Semaphore = asyncio.Semaphore(1)      # 실제 값은 main()에서 교체
```
**문제:** 테스트 시 상태 공유, 타입/값 불일치 위험  

```python
# After — 의존성 주입 + dataclass 캡슐화
@dataclass
class WorkerContext:
    queue: asyncio.Queue[_Job]
    semaphore: asyncio.Semaphore

async def create_worker_context(config: AppConfig) -> WorkerContext:
    return WorkerContext(
        queue=asyncio.Queue(maxsize=config.WORKER_QUEUE_SIZE),
        semaphore=asyncio.Semaphore(config.WORKER_MAX_CONCURRENT),
    )
```

---

### 🔴 Issue 2: `_notify` 함수 중복 노출 — `app/worker/agent.py:12`
```python
# Before — 내부 구현 세부사항이 public export 됨
from app.agent.graph import _notify, run_plan_task, run_task
__all__ = ["_notify", "_run_with_tools", "plan_and_run"]
```
**문제:** 언더스코어(`_notify`) 관례 위반, 캡슐화 파괴  

```python
# After — 공개 인터페이스만 노출
from app.agent.graph import notify as _graph_notify, run_plan_task, run_task

async def notify(text: str) -> None:
    """워커 레이어 알림 — graph 구현에 위임."""
    await _graph_notify(text)

__all__ = ["notify", "run_with_tools", "plan_and_run"]
```

---

### 🟡 Issue 3: `config.py` — 비밀키가 문자열 타입 노출
```python
# Before
CLAUDE_API_KEY: str = os.environ.get("CLAUDE_API_KEY", "")
```
**문제:** `repr()`, 로그, 직렬화 시 키 값이 그대로 노출될 위험  

```python
# After — SecretStr 래퍼 사용 (pydantic-settings 패턴)
from pydantic import SecretStr
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    CLAUDE_API_KEY: SecretStr = SecretStr("")
    TELEGRAM_TOKEN: SecretStr

    def get_claude_key(self) -> str:
        return self.CLAUDE_API_KEY.get_secret_value()

config = Settings()
```

---

### 🟡 Issue 4: `app/bot/server.py` — HOST 바인딩 하드코딩
```python
# Before
HOST = "0.0.0.0"  # 컨테이너 내부 — 외부 노출은 docker-compose 포트 매핑이 제어
```
**문제:** 주석 의존 보안, 환경별 재구성 불가  

```python
# After
HOST: str = os.environ.get("BOT_HOST", "127.0.0.1")  # 기본을 로컬호스트로
PORT: int = int(os.environ.get("BOT_PORT", "8765"))
```

---

### 🟡 Issue 5: `store.py` — `_now()` UTC 비권장 API 사용
```python
# Before
def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
```
**문제:** `utcnow()` 는 Python 3.12 에서 deprecated  

```python
# After — timezone-aware datetime 사용
def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
```

---

### 🟢 Issue 6: `app/pipeline/runner.py` — Claude 호출이 동기 블로킹
```python
# Before
def analyze_with_claude(prompt: str) -> str:   # 동기 함수
    response = client.messages.create(...)     # 블로킹 I/O
```
→ `asyncio.to_thread()` 로 우회하고 있으나 SDK가 async 지원함  

```python
# After — anthropic async SDK 직접 사용
async def analyze_with_claude(prompt: str) -> str:
    client = anthropic.AsyncAnthropic(api_key=config.CLAUDE_API_KEY)
    response = await client.messages.create(
        model=config.WORKER_MODEL,
        max_tokens=config.WORKER_MAX_TOKENS,
        system="...",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
```

---

## 4. 2026 트렌드 요약 체크리스트

| 항목 | 현황 | 비고 |
|------|------|------|
| 멀티 에이전트 (LangGraph) | ✅ 적용 | `agent/graph.py` |
| ReAct 패턴 | ✅ 적용 | `create_react_agent` |
| LLM 라우팅 / 하이브리드 | ✅ 적용 | Claude ↔ vLLM |
| RAG 파이프라인 | ✅ 적용 | `rag/retriever.py` |
| 비동기 전체 설계 (asyncio) | ✅ 적용 | aiohttp + asyncio |
| 관측성 (Prometheus/Grafana) | ✅ 적용 | `worker/metrics.py` |
| 컨테이너화 (Docker Compose) | ✅ 적용 | `docker-compose.yml` |
| K8s 매니페스트 | ✅ 존재 | `k8s/` |
| 비밀키 보안 (SecretStr) | ❌ 미적용 | `config.py` 개선 필요 |
| 의존성 주입 패턴 | ⚠️ 부분 | 전역 상태 혼재 |
| Async LLM SDK | ⚠️ 부분 | pipeline은 동기 사용 |
| timezone-aware datetime | ❌ 미적용 | `utcnow()` deprecated |

---

## 5. 핵심 개선 우선순위

```
🔴 High    1. config.py → pydantic-settings + SecretStr 도입
🔴 High    2. worker/server.py 전역 상태 → 의존성 주입으로 교체
🟡 Medium  3. pipeline/runner.py → AsyncAnthropic SDK 전환
🟡 Medium  4. store.py utcnow() → datetime.now(datetime.UTC) 교체
🟢 Low     5. bot/server.py HOST 환경변수화
🟢 Low     6. worker/agent.py _notify 내부 캡슐화 정리
```
