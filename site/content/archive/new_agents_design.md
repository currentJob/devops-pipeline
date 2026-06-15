---
title: "신규 에이전트 분야 설계 문서"
date: 2026-06-03
tags: [migrated]
source: migrated
publish: false
---

# 신규 에이전트 분야 설계 문서

> 작성일: 2026-06-03  
> 목적: 기존 멀티 에이전트 게이트웨이에 누락된 전문 에이전트 4종 추가

---

## 현황 갭 분석

| 기존 Route | 역할 | 커버하지 못하는 영역 |
|---|---|---|
| `code` | 버그·보안·리팩토링 분석 | 보안 특화 심층 분석 부재 |
| `doc` | README·API 문서 작성 | - |
| `infra` | Docker·CI/CD·인프라 | - |
| `stack` | IT 트렌드 리서치 → Notion | - |
| `general` | 자유형 질의 | - |
| `plan` | 복합 작업 분해(Planner) | 데이터/SQL, 성능, PR리뷰 부재 |

## 추가 에이전트 4종

### 1. `data` — 데이터 분석 / SQL / 스키마 에이전트
- **트리거 prefix**: `[DATA_TASK]`, Telegram 커맨드: `/data`
- **역할**: CSV·JSON·SQLite 분석, SQL 쿼리 작성·최적화, 스키마 설계 리뷰
- **시스템 프롬프트 특화**: pandas/polars 패턴, 인덱스 전략, N+1 탐지

### 2. `sec` — 보안 전문 에이전트
- **트리거 prefix**: `[SEC_TASK]`, Telegram 커맨드: `/sec`
- **역할**: OWASP Top 10 점검, 시크릿 노출 탐지, 의존성 CVE 리포트 해석, SAST 결과 분석
- **시스템 프롬프트 특화**: CVSS 기반 우선순위, 수정 PR 초안 제시

### 3. `perf` — 성능 프로파일링 에이전트
- **트리거 prefix**: `[PERF_TASK]`, Telegram 커맨드: `/perf`
- **역할**: Python 프로파일링 결과 해석, 비동기 병목 탐지, DB 쿼리 슬로우로그 분석, 메모리 누수 패턴
- **시스템 프롬프트 특화**: Big-O 분석, asyncio 이벤트 루프 블로킹, 캐싱 전략

### 4. `review` — PR 코드리뷰 에이전트
- **트리거 prefix**: `[REVIEW_TASK]`, Telegram 커맨드: `/review`
- **역할**: git diff 기반 코드리뷰, 변경 영향 분석, 테스트 커버리지 갭 지적, LGTM/수정요청 판정
- **시스템 프롬프트 특화**: 변경 최소성 원칙, 사이드이펙트 탐지, 보안 회귀 확인

## 변경 파일 목록

1. `app/agent/graph.py` — Route enum + _PREFIX_MAP + 4개 전문 에이전트 노드 + 라우터 분기 추가
2. `app/bot/commands/worker_cmd.py` — cmd_data / cmd_sec / cmd_perf / cmd_review 추가
3. `app/bot/commands/__init__.py` — register_commands 에 4개 핸들러 등록
4. `app/bot/commands/system.py` — /help 텍스트 업데이트
5. `tests/unit/test_new_agents.py` — 신규 에이전트 라우팅·시스템 프롬프트 단위 테스트
