# 경계 규칙 — 자동 실행 / 먼저 물어보기 / 절대 금지

## ✅ Always (확인 없이 실행)

**코드 품질**
- 린트 실행 (`uv run ruff check`)
- 타입 어노테이션 추가/수정
- 테스트 실행 (`uv run pytest`)
- 도구로 사실 확인 후 읽기 전용 응답

**읽기 전용 탐색**
- 파일 읽기, 심볼 검색, git log/diff/status
- docker compose ps/logs (읽기만)

**내 변경으로 생긴 정리**
- 내 코드가 만들어낸 미사용 import/변수 제거
- 내가 추가한 파일의 docstring 추가

---

## ⚠️ Ask First (먼저 사용자에게 확인)

- 파일/디렉토리 삭제
- `git push` 또는 원격 브랜치 변경
- 새 패키지 의존성 추가 (`uv add`)
- `docker-compose.yml` 포트·볼륨·네트워크 변경
- `.env` 또는 환경 변수 구조 변경
- 기존 API 엔드포인트 시그니처 변경
- SQLite 스키마 변경 (`store.py`)
- 작업에 무관한 코드 "개선" (리팩토링 요청 없음)

> **예외 — `/notes` 발행 적용**: 봇이 `main` 으로 push 하는 유일한 자동 경로.
> 의도적으로 허용하되 스테이징을 `site/content/` 경로로 한정(`git_ops.commit_paths`)하고
> 인라인 2차 확인 + 인가 chat 재확인으로 제한한다. 그 외 봇 push 는 여전히 human-gated.

---

## 🚫 Never (절대 금지)

- 시크릿 하드코딩 (API 키, 토큰, 비밀번호)
- `git push --force` (main 브랜치 대상)
- `--no-verify` 로 pre-commit 훅 우회
- 같은 접근법 3회 실패 후 동일 시도 반복
- 요청하지 않은 인접 코드 "개선"
- `data/tasks.db` 를 git에 커밋
- 테스트 없이 "작동할 것"이라고 단정
- `docker.sock` 마운트 — **`pocsandbox` 사이드카(profile poc) 단 하나만 예외**.
  bot/worker 등 다른 서비스엔 절대 마운트 금지(호스트 root 급 권한).

> **예외 — `/pocrun` 자동 파이프라인(autopilot)**: LLM 생성 PoC 코드를 실행하는 유일한 경로.
> bot `/pocrun` 인라인 확인 **1회**가 `worker /poc/autopilot` 의 빌드→수정→재빌드→평가
> 루프를 인가한다(빌드 실패 시 worker 가 PoC 소스를 **자동 수정**하므로 "워커는 코드 미수정"
> 원칙의 의도적 예외 — 단 쓰기는 `prompts/output/poc/<slug>/` 한정, `write_file` 강제).
> `docker.sock` 은 `pocsandbox` 에만 격리, 매 재빌드도 정적검사(privileged·host bind·sock·
> network_mode host·cap_add 거부) + 무-egress 실행(`--network none`) + 자원캡 + 타임아웃 +
> 자동 teardown 을 통과해야 한다. **보안 정적검사 위반(stage=check)은 자동 수정하지 않고 즉시
> 종료**(우회 시도 차단). 폭주는 `POC_AUTOPILOT_MAX_ITERATIONS` 캡으로 제한. 잔여위험은 security.md.
