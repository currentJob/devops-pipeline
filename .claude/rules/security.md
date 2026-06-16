# 보안 체크리스트

커밋 전 또는 코드 변경 후 반드시 확인.

## 시크릿 관리

- [ ] `CLAUDE_API_KEY`, `TELEGRAM_TOKEN`, `GITHUB_TOKEN`, `BRAVE_API_KEY` 하드코딩 없음
- [ ] `.env` 파일이 `.gitignore` 에 포함되어 있음
- [ ] 로그·알림 메시지에 토큰/키가 노출되지 않음

## 입력 검증

- [ ] 봇 커맨드 인자 (`context.args`) 길이 및 내용 검증
- [ ] `bash()` 도구에 사용자 입력이 직접 전달되지 않음 (명령 주입 방지)
- [ ] 파일 경로 인자가 허용된 디렉토리 내에 있음 (`read_file`, `write_file`)

## 워커 API

- [ ] `/run`, `/tasks`, `/health` 엔드포인트가 외부에 직접 노출되지 않음 (docker 네트워크 내부)
- [ ] 작업 결과를 외부 응답에 그대로 포함 시 오류 메시지에 스택트레이스 없음

## aiohttp / 외부 요청

- [ ] 모든 외부 요청에 `timeout=aiohttp.ClientTimeout(total=N)` 설정
- [ ] Brave Search API 응답 상태 코드 검증

## 파일 쓰기

- [ ] `write_file` 은 `prompts/output/` 하위에만 쓰도록 제한
- [ ] `vault_save` 는 `vault/`(VAULT_SUBDIR) 하위에만 쓰도록 제한 — 제목/카테고리 traversal 차단
- [ ] `data/tasks.db` 는 컨테이너 볼륨 관리 — 직접 수정 금지

## Docker

- [ ] `docker-compose.yml` 에 불필요한 포트 외부 노출 없음
- [ ] 컨테이너 간 통신은 내부 네트워크(`worker`, `bot` 서비스명) 사용
- [ ] `docker.sock` 은 `pocsandbox`(profile poc) 에만 마운트 — 다른 서비스 금지

## PoC 격리 실행 (`/pocrun`, pocsandbox)

LLM 생성 코드를 실행하는 유일한 경로 — **임의 코드 실행**임을 항상 인지.

- [ ] 실행 전 정적검사 통과: privileged·host bind·docker.sock·network_mode host/container·
      cap_add·devices·pid/ipc host·빌드 컨텍스트 경로 탈출 → 거부 (`app/pocsandbox/checks.py`)
- [ ] 런타임 `--network none` (무-egress) + `--cap-drop ALL` + `--security-opt no-new-privileges`
- [ ] mem/cpu/pids 캡 + build/run 타임아웃 + `finally` 자동 teardown(down -v, rm -f)
- [ ] pocsandbox 에 `.env`/시크릿 미주입, PoC 소스는 `:ro` 마운트
- [ ] 인라인 확인 + 인가 chat 재확인(휴먼게이트)

> **잔여 위험(완화 불가 인지)**: build 단계는 네트워크가 필요해 egress 존재(빌드시 탈취 가능성).
> docker.sock 보유 프로세스는 호스트 root 급 — 정적검사를 우회한 compose 의 탈출 가능성 0 아님(best-effort).
> 신뢰 가능한 PoC 에만 사용하고, 공유/프로덕션 호스트에서 남용 금지.
