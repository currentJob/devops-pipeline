---
title: "06 · 테스트 보고서 — 사이클 2 (.env 보호 + ruff + pip-audit)"
date: 2026-05-20
tags: [migrated]
source: migrated
---

# 06 · 테스트 보고서 — 사이클 2 (.env 보호 + ruff + pip-audit)

## 0. 요약
- **L1 단위**: 신규 작성 없음 (설정 변경이라 직접 단위 테스트 부적합). 기존 사이클1 의 5개 테스트가 영향 받지 않는지 회귀 확인 — 사용자 머신
- **L2 통합**: `uv sync` 가 ruff, pip-audit 신규 설치를 정상 처리하는지 — 사용자 머신
- **L3 컨테이너**: `.dockerignore` 에 `.env` 가 이미 있어 이미지 변경 0. dev 의존성은 prod 이미지에 포함되지 않음 (`uv sync --no-dev` 사용 중)
- **L4 회귀**: 기존 `app/*` 동작 무변경 (설정만 추가)
- **릴리스 가능 여부**: 🟡 **조건부** — 사용자 머신에서 § 2 명령 통과 + 05 보고서 § 3 의 시크릿 조치 완료 시 🟢

## 1. 환경 제약
샌드박스에서 ruff/pip-audit 설치 불가 (PyPI 접근 차단). 정적 검증만 수행.

## 2. 사용자 머신 실행 체크리스트

다음 5개를 순서대로 실행하고 각 결과를 기록한다.

### Step 1: 의존성 설치
```powershell
cd D:\devops-pipeline
uv sync
```
**기대**: ruff, pip-audit 가 `.venv` 에 설치되고 `uv.lock` 이 업데이트됨.

### Step 2: 기존 단위 테스트 회귀
```powershell
uv run pytest tests/unit/ -v
```
**기대**: 사이클1 의 5개 케이스 모두 통과.

### Step 3: ruff 린트
```powershell
uv run ruff check .
```
**기대 시나리오**:
- 깨끗 (0 경고): 다음 단계로
- 경고 5건 미만: 사용자가 보고 결정 (수동 수정 / `# noqa`)
- 경고 5건 이상: `uv run ruff check --fix --diff .` 로 자동 수정안 검토 후 `--fix` 적용 결정

### Step 4: ruff 포맷 점검
```powershell
uv run ruff format --check .
```
**기대**: 0 변경 또는 `uv run ruff format .` 으로 일괄 적용.

### Step 5: 의존성 취약점 스캔
```powershell
uv run pip-audit
```
**기대**: 알려진 CVE 0건. HIGH/CRITICAL 검출 시 즉시 업그레이드 또는 후속 티켓 발행.

## 3. 보안 조치 체크리스트 (05 보고서 § 3 후속)

L3 컨테이너 보안과 별개로, 시크릿 처리:

- [ ] `git rm --cached .env`
- [ ] `git add .gitignore .env.example pyproject.toml tools/ tests/ prompts/ CLAUDE.md`
- [ ] `git commit -m "🔒 .env 보호 + 워크플로 + ruff/pip-audit 도입"`
- [ ] Telegram Bot Token 회전 (@BotFather)
- [ ] Claude API Key 회전 (Anthropic 콘솔)
- [ ] (선택) `git filter-repo` 로 히스토리에서 .env 완전 제거
- [ ] `.env` 새 값으로 갱신

## 4. L3 컨테이너 / 공급망 — 영향 분석

| 항목 | 변경? | 근거 |
|---|---|---|
| Docker 이미지 크기 | ❌ | dev 의존성은 `uv sync --no-dev` 로 prod 이미지에서 제외 (Dockerfile:9) |
| `.env` 이미지 포함 | ❌ | `.dockerignore:5` 에 이미 `.env` 포함 |
| `.env.example` 이미지 포함 | ❌ | Dockerfile 이 `COPY app/` 만 함, 루트 파일 미복사 |
| SBOM 변동 | ❌ | runtime 의존성 추가 없음 |

## 5. L4 회귀 — 기존 동작

| 영역 | 변경? | 근거 |
|---|---|---|
| `app/*` 코드 | ❌ | 무변경 |
| 기존 파이프라인 동작 | ❌ | 설정만 추가, 로직 무변경 |
| 사이클1 의 `tools/notify.py` | ❌ | 영향 없음 |

## 6. 후속 작업 (Backlog)

| # | 항목 | 우선순위 | 사이클 |
|---|---|---|---|
| 1 | § 2 의 5개 명령 사용자 실행 + 결과 보고 | P0 | 본 사이클 종료 조건 |
| 2 | § 3 의 시크릿 조치 7개 항목 | P0 | 본 사이클 종료 조건 |
| 3 | ruff 경고 발견 시 수동/자동 수정 결정 | P1 | § 2 Step 3 결과 의존 |
| 4 | pre-commit hook 도입 (ruff + pip-audit 자동 실행) | P2 | 다음 사이클 02 리서치 |
| 5 | CI 파이프라인 (GitHub Actions) 작성 — 본 워크플로의 자동화 | P2 | 다음 사이클 |
| 6 | 회귀 테스트 `tests/regression/` (사이클1 의 백로그 #5) | P2 | 다음 사이클 |

## 7. 결론

> 🟡 **조건부 통과**:
> - 정적 검증 (TOML 구문, 패턴, placeholder 안전성) 통과
> - 실제 도구 실행 + 시크릿 조치는 사용자 머신에서 수행 필요
> - § 2 Step 1-5 통과 + § 3 시크릿 조치 완료 시 본 사이클 릴리스 가능
