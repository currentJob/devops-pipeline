import os

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"필수 환경변수 누락: {key}")
    return val


TELEGRAM_TOKEN: str = _require("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID: int = int(_require("TELEGRAM_CHAT_ID"))
CLAUDE_API_KEY: str = os.environ.get("CLAUDE_API_KEY", "")
APPROVAL_TIMEOUT: int = int(os.environ.get("APPROVAL_TIMEOUT", "300"))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
# Notion 통합 (선택 — /stack 명령어에서 사용)
NOTION_TOKEN: str = os.environ.get("NOTION_TOKEN", "")
NOTION_PARENT_PAGE_ID: str = os.environ.get("NOTION_PARENT_PAGE_ID", "")
# RAG 웹 검색 (선택 — Brave Search API 키, https://brave.com/search/api/)
BRAVE_API_KEY: str = os.environ.get("BRAVE_API_KEY", "")
# 워커 에이전트 튜닝
WORKER_BOT_NOTIFY_URL: str = os.environ.get("BOT_NOTIFY_URL", "http://bot:8765/notify")
WORKER_BOT_RESULT_URL: str = os.environ.get("BOT_RESULT_URL", "http://bot:8765/worker-result")
WORKER_MODEL: str = os.environ.get("WORKER_MODEL", "claude-sonnet-4-6")
WORKER_MAX_TOKENS: int = int(os.environ.get("WORKER_MAX_TOKENS", "8192"))
WORKER_MAX_ITERATIONS: int = int(os.environ.get("WORKER_MAX_ITERATIONS", "10"))
WORKER_TIMEOUT_S: float = float(os.environ.get("WORKER_TIMEOUT_S", "120"))
WORKER_URL: str = os.environ.get("WORKER_URL", "http://worker:8766/run")
WORKER_HEALTH_URL: str = os.environ.get("WORKER_HEALTH_URL", "http://worker:8766/health")
WORKER_TASKS_URL: str = os.environ.get("WORKER_TASKS_URL", "http://worker:8766/tasks")
WORKER_COMMIT_URL: str = os.environ.get("WORKER_COMMIT_URL", "http://worker:8766/git/commit")
WORKER_PUSH_URL: str = os.environ.get("WORKER_PUSH_URL", "http://worker:8766/git/push")
WORKER_MAX_CONCURRENT: int = int(os.environ.get("WORKER_MAX_CONCURRENT", "3"))
WORKER_QUEUE_SIZE: int = int(os.environ.get("WORKER_QUEUE_SIZE", "50"))
# 새 작업 시 참조할 직전 작업 요약본 개수 (0 = 비활성)
WORKER_MEMORY_COUNT: int = int(os.environ.get("WORKER_MEMORY_COUNT", "3"))
# 작업 이력 DB 백엔드 (sqlite | postgres). 기본 sqlite — 추가 인프라 불필요
DB_BACKEND: str = os.environ.get("DB_BACKEND", "sqlite").lower()
# DB_BACKEND=postgres 일 때 사용 (docker compose --profile postgres)
POSTGRES_HOST: str = os.environ.get("POSTGRES_HOST", "postgres")
POSTGRES_PORT: int = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_DB: str = os.environ.get("POSTGRES_DB", "tasks")
POSTGRES_USER: str = os.environ.get("POSTGRES_USER", "pipeline")
POSTGRES_PASSWORD: str = os.environ.get("POSTGRES_PASSWORD", "")
# vLLM (선택) — 설정 시 Claude API 대신 로컬 vLLM 사용
VLLM_ENDPOINT: str = os.environ.get("VLLM_ENDPOINT", "")
VLLM_MODEL: str = os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct")
# vLLM 총 컨텍스트 길이(입력+출력). docker-compose 의 --max-model-len 과 일치시킬 것
VLLM_MAX_MODEL_LEN: int = int(os.environ.get("VLLM_MAX_MODEL_LEN", "4096"))
# 로컬 git 커밋 (/commit 명령). 워커 컨테이너에서 사용할 커밋 아이덴티티
GIT_AUTHOR_NAME: str = os.environ.get("GIT_AUTHOR_NAME", "devops-pipeline bot")
GIT_AUTHOR_EMAIL: str = os.environ.get("GIT_AUTHOR_EMAIL", "bot@devops-pipeline.local")
# 원격 push (/push 명령) 용 GitHub PAT. 미설정 시 /push 는 비활성(안내만).
# Fine-grained PAT 권장 — 이 repo 한정, Contents: Read/Write. 절대 하드코딩·로그 노출 금지.
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
# 라우트별 백엔드 분기 — 여기 나열된 라우트만 vLLM, 나머지는 Claude (쉼표 구분)
VLLM_ROUTES: str = os.environ.get("VLLM_ROUTES", "general")
VLLM_ROUTES_SET: frozenset[str] = frozenset(r.strip() for r in VLLM_ROUTES.split(",") if r.strip())
