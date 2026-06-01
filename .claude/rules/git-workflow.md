# Git 워크플로 규칙

## 커밋 메시지 형식

```
Type: 한국어 설명 (명령형, 현재형)

- 변경 이유 또는 맥락
- 주요 변경 사항 (여러 파일/모듈 관련 시)
```

### Type 목록

| Type     | 용도                                         |
|----------|----------------------------------------------|
| Feat     | 새 기능 추가                                 |
| Fix      | 버그 수정                                    |
| Refactor | 동작 변경 없는 코드 구조 개선               |
| Docs     | 문서·주석 변경                              |
| Test     | 테스트 추가·수정                            |
| Chore    | 빌드·의존성·설정 변경 (pyproject, uv.lock)  |
| Perf     | 성능 개선                                    |
| Ci       | CI/CD 파이프라인 변경                        |

### 예시

```
Feat: LangGraph 멀티 에이전트 게이트웨이 도입

- code/doc/infra/stack/general 전문 에이전트 자동 분기
- SQLite 작업 이력 저장소 추가
```

```
Fix: create_react_agent state_modifier → prompt 파라미터 수정

langgraph-prebuilt 1.1.0 API 변경 대응
```

---

## 스테이징 원칙

- 관련 변경만 함께 커밋 (논리적 단위)
- `uv.lock` 은 의존성 변경 커밋에 함께 포함
- `data/*.db` 는 절대 스테이징하지 않음 (.gitignore 확인)
- `git add -A` 대신 파일명 명시

## 브랜치 전략

현재 프로젝트는 단일 `main` 브랜치 운영.
대규모 기능 개발 시에만 `feat/<short-description>` 브랜치 사용.
