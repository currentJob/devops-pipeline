# 보안 체크리스트

커밋 전 또는 코드 변경 후 반드시 확인.

## 시크릿 관리

- [ ] `CLAUDE_API_KEY`, `TELEGRAM_TOKEN`, `NOTION_TOKEN`, `BRAVE_API_KEY` 하드코딩 없음
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
- [ ] Notion API, Brave Search API 응답 상태 코드 검증

## 파일 쓰기

- [ ] `write_file` 은 `prompts/output/` 하위에만 쓰도록 제한
- [ ] `data/tasks.db` 는 컨테이너 볼륨 관리 — 직접 수정 금지

## Docker

- [ ] `docker-compose.yml` 에 불필요한 포트 외부 노출 없음
- [ ] 컨테이너 간 통신은 내부 네트워크(`worker`, `bot` 서비스명) 사용
