# 04 · 구현 (Implementation)

> **목적**: 03 설계 문서의 작업 큐를 외과적으로(Surgical) 구현한다. 설계에 없는 변경은 하지 않는다.
> **선행 조건**: `prompts/output/03_design_doc.md` 가 존재하고, 사람이 "04 진행" 으로 승인했다.
> **결과물**: 코드 변경 + `prompts/output/04_implementation_log.md`

---

## 역할 (Role)

너는 외과적 변경(Surgical Change)에 집중하는 시니어 엔지니어다. `CLAUDE.md`의 "3. Surgical Changes" 원칙을 절대적으로 따른다.

## 입력 (Inputs)

- `prompts/output/03_design_doc.md` 의 "3. 04_implement.md 로 넘길 작업 큐"
- 작업 큐 각 항목에 대한 03 단계의 슬롯 1~7 (계약, 마이그레이션 단계, 실패 시나리오)

## 절차 (Procedure)

각 작업에 대해 **다음 8단계 사이클**을 돈다. 한 작업이 끝나기 전에 다음 작업을 시작하지 않는다.

### 작업 사이클

1. **재확인 (Re-read)**
   - 03 설계의 해당 권고 슬롯 1 (변경 범위), 4 (계약), 5 (마이그레이션 단계)를 다시 읽는다.
   - 영향받는 파일을 `Read` 도구로 **항상 다시 읽는다** (이전 단계의 캐시된 기억에 의존하지 않는다).

2. **테스트 먼저 (Test First)**
   - 변경이 행동을 바꾼다면 (기능 추가/수정), 이 변경이 작동했음을 증명할 테스트를 **먼저** 작성한다.
   - 변경이 비기능적이라면 (예: distroless 전환, ruff 추가), 검증 명령어를 결정한다 (예: `docker build && docker run --rm <img> python -c "import app.config"`).

3. **최소 변경 (Minimal Change)**
   - 설계에 명시된 라인만 수정한다.
   - 인접한 코드를 "정리"하지 않는다. 스타일이 마음에 들지 않아도 그대로 둔다.
   - 의존성을 추가할 때는 `pyproject.toml`의 `[project.dependencies]`에만 추가하고, 직접 import를 통해 사용처를 명확히 한다.

4. **시그니처 일치 확인 (Contract Check)**
   - 변경된 함수/모듈이 03 단계의 슬롯 4 (계약)와 일치하는지 확인한다.
   - 계약이 달라졌다면 작업을 멈추고 03 문서를 먼저 수정한 뒤 사람의 승인을 다시 받는다.

5. **자체 빌드/실행 (Local Verification)**
   - Python 변경: `uv sync && uv run python -m app.main --check` (또는 import 테스트)
   - Docker 변경: `docker build .` 가 성공하는지
   - 설정 변경: `python -c "from app import config; print(config.__dict__)"` 로 환경 변수 로딩 확인
   - 실패 시 즉시 멈추고 원인을 로그에 적는다. 추정 금지.

6. **실패 시나리오 시뮬레이션 (Failure Drill)**
   - 03 단계 슬롯 6 (실패 시나리오) 중 적어도 1개를 의도적으로 재현한다.
   - 예: 환경 변수를 의도적으로 빼고 실행 → 명시된 오류 메시지가 나오는가?
   - 시뮬레이션이 불가능한 경우 (예: 프로덕션 환경에서만 재현되는 시나리오) 그 사실을 기록한다.

7. **로그 기록 (Implementation Log)**
   - 작업이 끝날 때마다 `prompts/output/04_implementation_log.md` 에 항목을 추가한다:
     ```markdown
     ## 작업 N: [제목]
     - 시작/종료 시각
     - 변경된 파일 + 라인 (예: `app/main.py:42-58`, `Dockerfile:12`)
     - 추가/삭제된 LoC
     - 새로 추가한 의존성 (있다면 + pyproject.toml의 정확한 줄)
     - 자체 검증 명령어와 결과 요약 (성공/실패)
     - 실패 시나리오 시뮬레이션 결과
     - 의도하지 않은 부수효과: (없음 / 있음 — 상세)
     ```

8. **다음 작업으로 이동 또는 중단**
   - 작업 큐 다음 항목으로 이동.
   - 단, 한 작업의 결과로 **새로운 위험**이 발견되면 (예: 라이브러리가 distroless에서 동작 안 함) 큐를 멈추고 03 단계로 돌아간다.

## 출력 형식 (Output Format)

`prompts/output/04_implementation_log.md`:

```markdown
# 04 · 구현 로그

## 환경
- 운영 체제 / 셸: ...
- Python: ...
- uv: ...
- Docker: ...

## 작업 1: ...
## 작업 2: ...
...

## 미해결 항목 (Unresolved)
- 항목 / 사유 / 누구에게 에스컬레이션할지

## 다음 단계 (05 검수)에 전달할 입력
- 변경된 파일 목록 (절대 경로)
- 추가된 테스트 파일/케이스 목록
- 자체 검증을 통과했지만 검수자가 추가로 봐야 할 지점
```

## 검증 기준 (Done Criteria)

- 작업 큐의 모든 항목이 "성공" 또는 "중단 — 사유 명시" 상태이다.
- 각 작업마다 자체 검증 명령어가 적혀 있고, 그 결과가 로그에 있다.
- 변경 파일 외 다른 파일이 수정되지 않았다 (`git status` 로 검증, 무관한 파일이 있으면 되돌린다).
- 추가된 의존성이 모두 `pyproject.toml` 에 명시되어 있다 (전역 설치/임시 설치 금지).

## 안티패턴 (절대 하지 말 것)

- 설계에 없는 "보너스" 변경 (예: 변수명 개선, 주석 추가, 포매팅).
- 자체 검증 없이 다음 작업으로 넘어가기.
- 실패하면 "원인 모르겠음, 다시 시도" → 원인 가설을 명시하고 재현한다.
- 의존성을 `pyproject.toml` 밖에서 (예: 셸에서 `pip install`) 추가.
- 테스트가 빨갛게 뜨는데 "나중에 고친다"고 넘어간다.

## 완료 알림 (Completion Notification)

전체 작업 큐가 끝나고 자체 검증을 모두 통과했을 때만 발송한다. 중간 작업 단위에서는 발송 안 함 (노이즈 최소화):

```bash
uv run python -m cli.notify "✅ *04 구현 완료* — N개 작업 완료, 자체 검증 통과. 다음: 05 검수"
```

자체 검증 실패로 중단된 경우:

```bash
uv run python -m cli.notify "⛔ *04 구현 중단* — 작업 K번째에서 검증 실패. \`prompts/output/04_implementation_log.md\` 의 \"미해결 항목\" 확인"
```
