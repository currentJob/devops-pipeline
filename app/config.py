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
# Obsidian vault — 지식/트렌드 노트 저장 폴더 (WORKSPACE 기준 하위 경로)
# 워커가 /workspace/<VAULT_SUBDIR> 에 .md 노트를 쓰고, 이 폴더를 Obsidian 으로 열어 관리.
VAULT_SUBDIR: str = os.environ.get("VAULT_SUBDIR", "vault")
# 벡터 인덱스 (Qdrant + fastembed 로컬 ONNX 임베딩) — vault 노트 의미 기반 검색.
# 미가용(Qdrant 연결 실패/비활성) 시 vault_search 는 키워드 검색으로 폴백한다.
VAULT_INDEX_ENABLED: bool = os.environ.get("VAULT_INDEX_ENABLED", "true").lower() == "true"
QDRANT_URL: str = os.environ.get("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION: str = os.environ.get("QDRANT_COLLECTION", "vault")
# fastembed ONNX 임베딩 모델 (다국어 — 한국어 지원). 변경 시 컬렉션 재인덱싱 필요.
EMBED_MODEL: str = os.environ.get(
    "EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
# onnxruntime 스레드 수 — 미설정 시 코어 수만큼 띄워 메모리가 크게 증가한다.
# 1 로 제한해 메모리·CPU 점유를 낮춤(재인덱싱은 약간 느려지나 read_only 컨테이너에 안전).
EMBED_THREADS: int = int(os.environ.get("EMBED_THREADS", "1"))
# 재인덱싱 임베딩 배치 크기 — 한 번에 메모리에 올리는 문서 수(피크 메모리 제한).
EMBED_BATCH_SIZE: int = int(os.environ.get("EMBED_BATCH_SIZE", "16"))
# Qdrant 클라이언트 요청 타임아웃(초) — 미가용 시 빠른 폴백을 위해 짧게.
QDRANT_TIMEOUT_S: float = float(os.environ.get("QDRANT_TIMEOUT_S", "3"))
# RAG 웹 검색 (선택 — Brave Search API 키, https://brave.com/search/api/)
BRAVE_API_KEY: str = os.environ.get("BRAVE_API_KEY", "")
# 최신 자료 조사 (last30days 스킬) — 에이전트가 시의성 있는 주제에 호출하는 recent_research 도구
# 비활성 시 도구는 에이전트에 노출되지 않음. Reddit/HN 은 키 없이 동작.
RESEARCH_ENABLED: bool = os.environ.get("RESEARCH_ENABLED", "true").lower() == "true"
# 조회 소스 (쉼표 구분). 키리스 기본값. X/YouTube 등은 해당 API 키 설정 시 추가 가능.
RESEARCH_SOURCES: str = os.environ.get("RESEARCH_SOURCES", "reddit,hackernews")
# 조회 기간(일)
RESEARCH_DAYS: int = int(os.environ.get("RESEARCH_DAYS", "30"))
# CLI 1회 실행 타임아웃(초) — 워커 전체 타임아웃보다 작게 유지
RESEARCH_TIMEOUT_S: float = float(os.environ.get("RESEARCH_TIMEOUT_S", "90"))
# vendored last30days.py 경로 재정의 (빈 값이면 리포 내 vendor/ 기본 경로 사용)
RESEARCH_SCRIPT: str = os.environ.get("RESEARCH_SCRIPT", "")
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
WORKER_VAULT_REINDEX_URL: str = os.environ.get(
    "WORKER_VAULT_REINDEX_URL", "http://worker:8766/vault/reindex"
)
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
