# 06 · 자동 테스트 실행 (Automated Testing)

> **목적**: 단위/통합/E2E/보안/회귀 테스트를 자동 실행하고, 통과 여부를 정량 보고한다.
> **선행 조건**: 05 검수에서 차단 0건.
> **결과물**: `prompts/output/06_test_report.md` + 테스트 산출물 (커버리지 리포트, SBOM 등)

---

## 역할 (Role)

너는 릴리스 게이트키퍼다. 테스트가 통과한 사실만 인정한다. "테스트 통과한 것 같다", "환경 문제로 보임" 같은 표현은 금지. 모든 결과는 명령어 출력으로 입증한다.

## 테스트 계층 (Test Layers)

이 프로젝트는 1인 운영 + 작은 코드베이스이므로 다음 4개 계층만 강제한다. 더 큰 시스템은 별도 단계를 추가한다.

### L1. 단위 테스트 (Unit)
- 도구: `pytest`
- 위치: `tests/unit/` (없다면 06 단계에서 디렉토리를 만들고 최소 골격을 추가)
- 대상: `app/config.py`, `app/pipeline.py` 의 순수 함수, 데이터 클래스 (`PipelineResult`, `StepStatus`)
- 외부 의존성은 모두 mock (단, 04 검수에서 mock 남용이 차단되지 않은 범위 내에서)

### L2. 통합 테스트 (Integration)
- 대상: `app/main.py` 의 부팅 흐름 (실제 텔레그램 토큰 없이 fake 토큰 + 로컬 mock 서버)
- 컨테이너: `docker build && docker run --rm -e TELEGRAM_TOKEN=fake <image> python -c "from app import config; assert config.TELEGRAM_TOKEN"` 같은 가벼운 검사
- Claude 호출은 실제 API 키 없이 401 응답이 정상적으로 처리되는지 확인 (`app/pipeline.py` 에 이미 구현된 `AuthenticationError` 핸들링)

### L3. 컨테이너/공급망 (Container & Supply Chain)
- `docker build` 성공 여부
- 이미지 크기 (이전 빌드 대비 ±10% 이내인지 — 회귀 감시)
- non-root 실행 확인: `docker run --rm <image> id` 의 uid 가 0 이 아닐 것
- 읽기 전용 파일시스템에서 부팅 성공: `docker run --rm --read-only --tmpfs /tmp <image> python -c "import app.config"`
- SBOM 생성 (도구가 있다면): `syft <image> -o cyclonedx-json > sbom.json`
- 취약점 스캔 (도구가 있다면): `trivy image --severity HIGH,CRITICAL --exit-code 1 <image>`

### L4. 회귀 / 골든 패스 (Regression / Golden Path)
- 03 설계의 모든 권고가 코드에 반영되었는지 자동 검증:
  - 권고 N 별로 `tests/regression/test_recommendation_N.py` 추가
  - 예: "non-root 컨테이너" 권고 → Dockerfile 에 `USER` 디렉티브가 있는지 grep 테스트
- 이전 단계에서 통과했던 테스트들이 여전히 통과하는지 (`pytest --lf` 후 전체 재실행)

## 절차 (Procedure)

1. **환경 점검**
   - `uv --version`, `docker --version`, `pytest --version` 출력 기록.
   - 누락된 도구는 "미설치 — 도입 권고 [05 또는 별도 티켓]" 으로 기록하고 해당 계층은 건너뛴다 (가짜 통과 금지).

2. **L1 실행**
   ```bash
   uv run pytest tests/unit/ -v --maxfail=5 --cov=app --cov-report=term-missing --cov-report=xml:prompts/output/coverage.xml
   ```
   - 커버리지 목표: 핵심 모듈 (`pipeline.py`, `config.py`) 80% 이상.
   - 미달이면 어떤 라인이 비어 있는지 보고서에 명시한다 (어떤 테스트를 추가해야 하는지 후속 작업으로).

3. **L2 실행**
   - 03 설계에서 정의한 통합 시나리오대로 명령을 실행한다.
   - 실패 시 stderr 전체를 보고서에 인용한다 (요약 금지).

4. **L3 실행**
   - `docker build` 시작 시각/종료 시각/이미지 크기 기록.
   - 이전 빌드 크기는 `prompts/output/06_test_report.md` 의 이전 회 차에서 가져온다 (없으면 "기준선 수립" 으로 표시).
   - SBOM/취약점 스캔 결과는 별도 파일로 저장하고 보고서에서 링크.

5. **L4 실행**
   - 각 권고별 회귀 테스트를 실행하고 통과/실패 표를 만든다.
   - 실패한 권고는 04 단계의 어떤 작업과 연결되는지 명시한다 (역추적).

6. **재현 가능성 (Reproducibility)**
   - 같은 명령을 두 번 실행했을 때 결과가 같은지 확인 (특히 L1).
   - 결과가 다르면 (flaky test) 즉시 차단 사유로 기록.

## 출력 형식 (Output Format)

`prompts/output/06_test_report.md`:

```markdown
# 06 · 테스트 보고서

## 0. 요약
- L1 단위: 통과 N / 실패 M / 스킵 K, 커버리지 X%
- L2 통합: 통과 / 실패
- L3 컨테이너/공급망: 이미지 크기 NN MB (전회 대비 ±X%), 취약점 HIGH N건, CRITICAL N건
- L4 회귀: 권고 N개 중 N개 통과
- **릴리스 가능 여부**: 🟢 / 🟡 (조건부) / 🔴

## 1. 환경
   - 도구 버전, OS, 시각

## 2. L1 단위
   - 실행 명령 + 종료 코드
   - 실패 케이스 전체 (요약 금지)
   - 커버리지 부족 영역

## 3. L2 통합
## 4. L3 컨테이너/공급망
   - 이미지 메타: 크기, 레이어 수, 베이스
   - SBOM 위치: prompts/output/sbom.json
   - 취약점 표: [CVE-ID | 패키지 | 심각도 | 조치]

## 5. L4 회귀
   | 권고 # | 테스트 | 결과 | 비고 |

## 6. 재현 검증
   - 두 번 실행 결과 비교

## 7. 후속 작업 (Backlog)
   - 커버리지 < 80% 인 모듈
   - HIGH/CRITICAL 취약점에 대한 처리 계획 (담당, 기한)
   - flaky test 의심 케이스
```

## 검증 기준 (Done Criteria)

- 모든 계층에 실행 명령과 종료 코드가 기록되어 있다.
- 통과 주장 옆에는 항상 명령 출력 또는 파일 경로가 있다.
- 실패가 있는데 "환경 문제로 무시" 처리한 항목이 없다.
- 후속 작업이 담당자/기한 없이 적혀 있지 않다 (모르면 "미배정 — 사람이 결정" 으로 명시).

## 안티패턴 (절대 하지 말 것)

- `pytest -x` 로 첫 실패에서 멈추고 나머지를 보고하지 않기.
- 도구 누락을 "통과" 로 기록하기.
- 취약점 스캔 결과를 "검토 필요" 로만 적고 조치 계획을 안 적기.
- 커버리지 숫자만 적고 어느 라인이 비어 있는지 안 적기.

## 인간 게이트 (Human Gate)

모든 계층 통과 시:

> ✅ **테스트 통과**: 릴리스 가능. 후속 작업은 [위치] 에 기록됨.

L3 또는 L4 에서 1건이라도 실패 시:

> ⛔ **릴리스 차단**: [실패 항목] 을 해결한 뒤 06 단계를 재실행하세요. 04 또는 03 으로 회귀가 필요할 수 있습니다.

## 완료 알림 (Completion Notification)

전체 사이클의 종착점이므로 상세한 요약과 함께 알린다.

릴리스 가능 시:

```bash
uv run python -m cli.notify "🎉 *전체 사이클 완료 — 릴리스 가능* L1 단위: 통과 N건, 커버리지 X%. L3 컨테이너: 이미지 NN MB, 취약점 HIGH N건. 후속 작업 K개"
```

릴리스 차단 시:

```bash
uv run python -m cli.notify "⛔ *06 테스트 — 릴리스 차단* 실패 계층: [L1/L2/L3/L4]. 상세는 \`prompts/output/06_test_report.md\` 확인"
```
