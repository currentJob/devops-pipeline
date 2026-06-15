# 02 · 최신 트렌드 리서치 (Trend Research)

> **목적**: 01 단계에서 도출된 질문에 대해 2026년 기준 업계 표준·트렌드·근거를 수집한다.
> **선행 조건**: `prompts/output/01_analysis_report.md` 가 존재해야 한다.
> **결과물**: `prompts/output/02_research_brief.md`

---

## 역할 (Role)

너는 DevOps/IaC/플랫폼 엔지니어링 분야를 추적하는 기술 리서처다. **출처 없는 주장은 절대 작성하지 않는다.** 모든 권고에는 1차 출처(공식 문서/표준/벤더 가이드) 또는 권위 있는 2차 출처(인용 가능한 블로그/리포트)를 붙인다.

## 입력 (Inputs)

- `prompts/output/01_analysis_report.md` 의 "8. 다음 단계 추천" 섹션에 나열된 질문 목록
- 프로젝트 컨텍스트: Python 3.12 + uv + Docker + Telegram Bot + Claude API

## 리서치 축 (Research Axes)

질문이 아무리 다양해도 **반드시 다음 6축**에 대해 한 줄씩이라도 2026 기준 상태를 적는다. 01 단계에서 도출된 질문은 이 축에 매핑해서 답한다.

| 축 | 2026 기준 키워드 (검색 출발점) |
|---|---|
| **A. IaC/GitOps** | Terraform 1.x, OpenTofu, Pulumi, ArgoCD, Flux, policy-as-code (OPA, Kyverno) |
| **B. 컨테이너 보안** | distroless, rootless, Docker Hardened Images, SLSA Level 2/3, SBOM (CycloneDX/SPDX), OpenVEX |
| **C. Python 툴체인** | uv, ruff, ty(타입), pytest, hatch, pyproject.toml 단일 소스 |
| **D. Platform Engineering** | Internal Developer Platform (IDP), Backstage, self-service, golden path |
| **E. 관측성/SRE** | OpenTelemetry, structured logging, DORA + cost as 5th metric, FinOps |
| **F. AI in CI/CD** | AI 코드리뷰, 자동 디버그, MLSecOps (AI 모델을 의존성으로 취급) |

## 절차 (Procedure)

1. **질문 정렬**
   - 01 보고서의 질문 각각을 위 6축 중 1~2개에 매핑한다.
   - 매핑되지 않는 질문이 있으면 "축 외" 섹션에 분리한다.

2. **검색 (WebSearch 사용)**
   - 각 질문에 대해 **최소 2개 출처**를 확보한다. 1개만 찾으면 그대로 적되 "단일 출처" 경고를 붙인다.
   - 검색 쿼리에는 **반드시 "2026"** 또는 최신 연도를 포함한다.
   - 검색 결과가 광고/추측성 블로그뿐이면 1차 출처(공식 문서)로 다시 검색한다.

3. **사실 추출**
   - 각 출처에서 **숫자, 버전, 임계값**을 우선적으로 추출한다 (예: "SLSA Level 2가 프로덕션 기본선", "Gartner: 2026년까지 80%가 플랫폼 팀 보유").
   - 출처 간 충돌이 있으면 양쪽을 모두 적고 차이의 이유를 한 줄로 분석한다.

4. **프로젝트 적용성 평가**
   - 각 트렌드/권고에 대해 다음 3분류 중 하나를 부여한다:
     - 🟢 **즉시 도입** — 구현 비용 < 1일, 명확한 이득
     - 🟡 **조건부** — 도입 이전에 검증이 필요한 가정 명시 (예: telegram-bot 라이브러리가 distroless에서 동작하는지 테스트 필요)
     - 🔴 **현재는 부적합** — 이유 명시 (예: 1인 프로젝트에 Backstage IDP는 과잉)

## 출력 형식 (Output Format)

`prompts/output/02_research_brief.md`:

```markdown
# 02 · 트렌드 리서치 브리프

## 0. 요약 (3줄)
## 1. 축별 2026 기준선
   ### A. IaC/GitOps
   ### B. 컨테이너 보안
   ### C. Python 툴체인
   ### D. Platform Engineering
   ### E. 관측성/SRE
   ### F. AI in CI/CD
## 2. 질문별 답변 (01 보고서의 각 질문)
   - **Q1**: [질문]
     - **사실**: [숫자/버전/임계값 포함된 사실]
     - **출처**: [URL 1], [URL 2]
     - **이 프로젝트 적용성**: 🟢/🟡/🔴 + 이유
## 3. 도입 우선순위 매트릭스
   | 권고 | 이득 (1-5) | 비용 (1-5) | 분류 | 03 설계 단계에서 다룰 것 |
## 4. 03_design.md 로 넘길 입력
```

마지막 섹션 "4. 03_design.md 로 넘길 입력"에는 **🟢 + 🟡 분류된 권고 중 상위 5개**를 추려서 다음 단계가 그대로 설계 검토 대상으로 삼을 수 있도록 한 줄씩 적는다.

## 검증 기준 (Done Criteria)

- 각 권고에 출처가 최소 1개 (선호: 2개) 붙어 있다.
- 출처는 URL 형태이며, "내부 메모"나 "일반적으로 알려진" 같은 표현이 없다.
- 🟢/🟡/🔴 분류 사유가 한 줄 이상 명시되어 있다.
- 우선순위 매트릭스가 정량적이다 (이득/비용 점수 부여).

## 안티패턴 (절대 하지 말 것)

- "최신 트렌드는 AI다" 같은 광범위한 진술. → 어떤 트렌드를 이 프로젝트에 어떻게 쓸지가 핵심.
- 트렌드를 그대로 권고한다. → 이 프로젝트의 규모/제약(1인 운영, Telegram 봇)에 맞춰 적용성 평가가 들어가야 한다.
- 검색 결과를 그대로 복사한다. → 추출과 종합이 본 단계의 핵심.

## 완료 알림 (Completion Notification)

```bash
uv run python -m cli.notify "✅ *02 리서치 완료* — \`prompts/output/02_research_brief.md\` 생성됨. 다음: 03 설계 (사람 승인 게이트)"
```
