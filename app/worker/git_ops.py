"""로컬 git 커밋 전용 모듈 (원격 push 미포함).

워커 컨테이너의 /workspace 바인드 마운트(rw)에서 결정론적 git 명령을 실행한다.
LLM 은 커밋 메시지 *생성* 에만 쓰고, 실제 add/commit 은 고정 인자 명령으로 수행한다.
에이전트의 bash 도구(읽기 전용 allowlist)와는 분리된 경로다 — 쓰기 git 은 여기서만.
"""

from __future__ import annotations

import asyncio
import logging

from app import config

logger = logging.getLogger(__name__)

WORKSPACE = "/workspace"
_GIT_TIMEOUT_S = 20
DIFF_MAX_CHARS = 12000  # LLM 입력 토큰 보호

# host 소유 repo 의 dubious ownership 경고 회피 + 커밋 아이덴티티 주입(전역 설정 쓰기 불필요)
_GIT_BASE: tuple[str, ...] = (
    "git",
    "-C",
    WORKSPACE,
    "-c",
    "safe.directory=*",
    "-c",
    f"user.name={config.GIT_AUTHOR_NAME}",
    "-c",
    f"user.email={config.GIT_AUTHOR_EMAIL}",
)

_COMMIT_SYSTEM = """당신은 git 커밋 메시지 작성 전문가입니다.
주어진 변경 내역(git status, diff)을 보고 이 프로젝트 규칙에 맞는 한국어 커밋 메시지를 작성하세요.

형식:
Type: 한국어 설명 (명령형·현재형, 50자 이내)

- 변경 이유나 맥락 (필요 시 1~3개 불릿)

Type 목록: Feat(새 기능), Fix(버그 수정), Refactor(동작 변경 없는 구조 개선),
Docs(문서·주석), Test(테스트), Chore(빌드·의존성·설정), Perf(성능), Ci(CI/CD)

규칙:
- 커밋 메시지 본문만 출력. 설명·인사·코드블록 마커(```) 금지.
- 변경의 핵심을 제목 한 줄로 요약하고, 필요하면 불릿로 맥락만 덧붙인다."""


async def _git(*args: str) -> tuple[int, str]:
    """git 명령 실행 → (returncode, 합쳐진 stdout/stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *_GIT_BASE,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await asyncio.wait_for(proc.communicate(), timeout=_GIT_TIMEOUT_S)
    return proc.returncode, out.decode("utf-8", errors="replace").strip()


async def collect_changes() -> tuple[str, str]:
    """(status_short, diff) 반환. 커밋할 변경이 없으면 ('', '')."""
    rc, status = await _git("status", "--short")
    if rc != 0:
        raise RuntimeError(f"git status 실패: {status}")
    if not status:
        return "", ""
    _, diff = await _git("diff", "HEAD")  # tracked 변경 (untracked 내용은 status 로 노출)
    if len(diff) > DIFF_MAX_CHARS:
        diff = diff[:DIFF_MAX_CHARS] + "\n...(diff 잘림)"
    return status, diff


def _strip_fences(text: str) -> str:
    """모델이 메시지를 ``` 로 감쌌을 때 펜스 줄만 제거."""
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


async def generate_message(status: str, diff: str) -> str:
    """변경 내역으로부터 커밋 메시지를 생성."""
    from app.agent import runtime

    content = await runtime.chat(
        system=_COMMIT_SYSTEM,
        user=(
            f"[git status]\n{status}\n\n"
            f"[git diff]\n{diff or '(텍스트 diff 없음 — 신규/바이너리 파일)'}"
        ),
    )
    return _strip_fences(content)


async def apply_commit(message: str) -> str:
    """변경 전체를 스테이징하고 커밋. 마지막 커밋 한 줄(oneline)을 반환. push 안 함."""
    rc, out = await _git("add", "-A")
    if rc != 0:
        raise RuntimeError(f"git add 실패: {out}")
    rc, out = await _git("commit", "-m", message)
    if rc != 0:
        raise RuntimeError(f"git commit 실패: {out}")
    _, head = await _git("log", "-1", "--oneline")
    return head


# ── 원격 push (/push 명령) ────────────────────────────────────────────────────


def _redact(text: str) -> str:
    """출력/에러에서 토큰 문자열을 가린다 (로그·응답 노출 방지)."""
    return text.replace(config.GITHUB_TOKEN, "***") if config.GITHUB_TOKEN else text


def _authenticated_url(origin: str, token: str) -> str:
    """https 원격 URL 에 토큰을 끼운다 (.git/config 에 저장하지 않고 1회용 인자로만 사용)."""
    prefix = "https://"
    if not origin.startswith(prefix):
        raise RuntimeError(f"HTTPS 원격만 지원합니다: {origin}")
    return f"{prefix}x-access-token:{token}@{origin[len(prefix) :]}"


async def current_branch() -> str:
    rc, out = await _git("rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        raise RuntimeError(f"현재 브랜치 조회 실패: {out}")
    return out


async def pending_commits(branch: str) -> str | None:
    """origin/<branch> 대비 push 대기 커밋(oneline).

    반환: None = 업스트림 없음(신규 브랜치) / "" = 최신 / 그 외 = 대기 커밋 목록.
    """
    rc, _ = await _git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}")
    if rc != 0:
        return None
    _, out = await _git("log", f"origin/{branch}..HEAD", "--oneline")
    return out


async def push(branch: str) -> str:
    """현재 HEAD 를 origin/<branch> 로 push. 토큰은 1회용 URL 인자로만 전달."""
    if not config.GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN 미설정 — .env 에 GitHub PAT 추가 필요")
    rc, origin = await _git("remote", "get-url", "origin")
    if rc != 0:
        raise RuntimeError(f"origin 원격 조회 실패: {origin}")
    auth_url = _authenticated_url(origin, config.GITHUB_TOKEN)
    rc, out = await _git("push", auth_url, f"HEAD:{branch}")
    out = _redact(out)
    if rc != 0:
        raise RuntimeError(f"git push 실패: {out}")
    return out or f"{branch} → origin push 완료"
