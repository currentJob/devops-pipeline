# 자동화 워크플로 프롬프트 세트

> **대상 프로젝트**: `D:\devops-pipeline` (Python 3.12 · uv · Docker · Telegram 봇 · Claude API)
> **기준 연도**: 2026 — DevOps/IaC 트렌드 반영
> **사용 방식**: Claude (또는 다른 LLM 코딩 에이전트) 에게 각 단계 파일을 순서대로 입력으로 준다.

---

## 한 줄 요약

분석 → 리서치 → 설계 → 구현 → 검수 → 테스트의 **6단계 파이프라인** 으로, 각 단계는 이전 단계의 산출물을 **명시된 위치에서 읽고**, 다음 단계에 **명시된 입력을 넘긴다.** 모든 단계에 검증 기준과 인간 승인 게이트가 있다.

## 파일 구조

```
D:\devops-pipeline\
├── prompts\
│   ├── 00_README.md          ← 이 문서 (전체 인덱스)
│   ├── 01_analyze.md         ← 프로젝트 진단
│   ├── 02_research.md        ← 2026 트렌드 리서치
│   ├── 03_design.md          ← 아키텍처 설계 + 인간 게이트
│   ├── 04_implement.md       ← 외과적 구현
│   ├── 05_review.md          ← 코드 품질 검수 + 인간 게이트
│   ├── 06_test.md            ← 자동 테스트 + 릴리스 게이트
│   └── output\               ← 각 단계의 보고서가 저장되는 곳
└── (기존 프로젝트 파일)
```

## 단계 흐름

| # | 파일 | 입력 | 출력 | 게이트 |
|---|---|---|---|---|
| 01 | `01_analyze.md` | 프로젝트 디렉토리 전체 | `output/01_analysis_report.md` | 자동 진행 |
| 02 | `02_research.md` | 01의 "다음 단계 질문" | `output/02_research_brief.md` | 자동 진행 |
| 03 | `03_design.md` | 02의 "넘길 입력" | `output/03_design_doc.md` | ⏸️ **사람 승인 필수** |
| 04 | `04_implement.md` | 03의 작업 큐 | 코드 변경 + `output/04_implementation_log.md` | 자체 검증 |
| 05 | `05_review.md` | 04 로그 + `git diff` | `output/05_review_report.md` | ⏸️ **사람 승인 필수** |
| 06 | `06_test.md` | 05 통과 보고 | `output/06_test_report.md` + SBOM/커버리지 | 🚦 **릴리스 게이트** |

## 사용법 (Claude 에서)

### 1회 실행 (전체 사이클)

각 단계 파일의 내용을 Claude 에게 그대로 프롬프트로 주고, 출력이 명시된 위치에 저장되었는지 확인한 뒤 다음 단계로 넘어간다.

예시:

```text
[당신이 Claude 에게 보내는 메시지]

D:\devops-pipeline\prompts\01_analyze.md 파일을 읽고, 그 안의 절차에 따라
이 프로젝트를 분석한 뒤 prompts\output\01_analysis_report.md 에 보고서를 작성해줘.
```

01 이 끝나면:

```text
prompts\output\01_analysis_report.md 가 작성되었는지 확인하고,
다음으로 prompts\02_research.md 를 실행해줘.
```

### 부분 재실행

- 코드만 바뀌고 설계는 그대로면 → `04 → 05 → 06` 만 다시 돌린다.
- 설계가 바뀌면 → `03 → 04 → 05 → 06` 을 다시 돈다.
- 분석이 오래된 것 같으면 (3개월 이상) → 01 부터 다시.

### CI 에 연결하기

각 단계는 결정적 산출물을 만들도록 설계되었다. GitHub Actions / GitLab CI 에서 다음처럼 묶을 수 있다:

```yaml
# .github/workflows/auto-pipeline.yml (예시 — 실제 작성은 06 단계 통과 후)
jobs:
  analyze:
    # 01_analyze.md 를 Claude API 에 보내고 결과를 PR 코멘트로
  research:
    needs: analyze
  design:
    needs: research
    # 03 출력은 PR review 요청으로 변환 — 사람 승인 필요
  test:
    needs: design  # 04, 05 는 로컬/PR 작업, 06 만 CI 강제
    # ruff, pytest, docker build, trivy, syft 실행
```

## 설계 원칙

이 워크플로는 다음 5가지 원칙 위에 만들어졌다.

1. **선(先) 분석, 후(後) 권고** — 코드를 읽지 않고 일반론을 적지 않는다. 01 → 02 분리의 이유.
2. **대안 비교 강제** — 모든 설계 결정에 "현상유지" 옵션 + 최소 1개 대안. (03 단계 슬롯 2)
3. **외과적 변경** — 설계에 없는 변경 금지. `CLAUDE.md` 의 "3. Surgical Changes" 와 일치.
4. **검증 가능한 완료 기준** — 각 단계마다 "Done Criteria" 가 있어 LLM 이 스스로 완료 여부를 판정 가능.
5. **인간 게이트** — 설계(03)와 검수(05)는 반드시 사람 검토. 자동 머지 금지.

## 2026 트렌드 반영 포인트

각 단계가 어떤 최신 트렌드를 반영했는지 표로 정리:

| 단계 | 반영된 2026 트렌드 |
|---|---|
| 01 | living SBOM 사고방식 (인벤토리·의존성 그래프 분리), 컨테이너 표면 점검 (distroless, rootless) |
| 02 | Platform Engineering 80% 채택, GitOps + IaC 2.0, AI-CI/CD, MLSecOps, FinOps as 5th DORA |
| 03 | policy-as-code 사전 검토, 롤백 단위 정의 (GitOps 회복력) |
| 04 | uv + ruff + pyproject.toml 단일 소스, 의존성 추가의 명시성 |
| 05 | SLSA 사고방식 (build provenance), CVE 알림 추적, SBOM 자동 생성 |
| 06 | CycloneDX/SPDX SBOM, Trivy 스캔, 재현 가능성 검증, DORA + 비용 메트릭 |

## FAQ

**Q. 1인 프로젝트인데 6단계가 너무 무겁지 않나?**
A. 첫 1회만 무겁다. 02, 03 의 결과물은 재사용된다. 일상 작업은 보통 04~06 만 돈다.

**Q. Claude 가 02 단계에서 잘못된 트렌드를 가져오면?**
A. 02 의 검증 기준에 "출처 최소 1개 필수" 가 있다. 03 단계에서 다시 적용성 평가를 한다. 그래도 의심스러우면 사람이 03 게이트에서 거른다.

**Q. 05 의 자동 점검 도구가 설치 안 되어 있다.**
A. 05 는 "미설치 — 도입 권고" 로 기록한다. 다음 사이클의 02~03 에서 그 도구 도입 자체를 권고 항목으로 다룬다.

**Q. 06 의 회귀 테스트는 누가 처음에 만드나?**
A. 04 단계에서 각 작업이 끝날 때마다 해당 권고에 대한 회귀 테스트를 `tests/regression/` 에 추가한다. 처음에는 비어 있고 점진적으로 쌓인다.

## 출처

- DevOps/IaC 트렌드: [DevOps.com — Top 15 DevOps Trends 2026](https://devops.com/top-15-devops-trends-to-watch-in-2026/), [Gartner Platform Engineering 80% 예측](https://www.webpronews.com/platform-engineerings-devops-overhaul-80-adoption-by-2026/)
- Python 툴체인: [KDnuggets — Python Project Setup 2026: uv + Ruff](https://www.kdnuggets.com/python-project-setup-2026-uv-ruff-ty-polars)
- 공급망 보안: [Cloudsmith — 2026 Guide to Software Supply Chain Security](https://cloudsmith.com/blog/the-2026-guide-to-software-supply-chain-security-from-static-sboms-to-agentic-governance), [Practical DevSecOps — SLSA Framework Guide](https://www.practical-devsecops.com/slsa-framework-guide-software-supply-chain-security/)
- 컨테이너 보안: [Docker Docs — Distroless 이미지](https://docs.docker.com/dhi/core-concepts/distroless/), [MrCloudBook — Docker Hardened Images 2026](https://mrcloudbook.com/docker-hardened-images-the-2026-architects-guide-to-supply-chain-compliance/)
