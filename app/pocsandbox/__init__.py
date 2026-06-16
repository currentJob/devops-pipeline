"""PoC 격리 실행 사이드카.

LLM 이 생성한 PoC(prompts/output/poc/<slug>/)를 격리 환경에서 build + 단일 실행해
디버깅 로그를 돌려준다. docker.sock 은 이 서비스에만 격리되며, 정적 검사(checks)로
호스트 탈출 directive 를 차단한다. (잔여 위험은 boundaries.md/security.md 참조)
"""
