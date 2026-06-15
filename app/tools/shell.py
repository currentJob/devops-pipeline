from __future__ import annotations

import asyncio
import re
import shlex

BASH_TIMEOUT_S = 30
SHELL_METAS = re.compile(r"[;&|`<>$]")

BASH_ALLOWLIST: tuple[str, ...] = (
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "git status",
    "git diff",
    "git log",
    "git ls-files",
    "git show",
    # dev 이미지(runtime-dev)에 포함된 도구 — /lint·/test·/audit 가 직접 호출
    "ruff",
    "pytest",
    "pip-audit",
    # dev 환경(uv 존재) 호환용
    "uv run pytest",
    "uv run ruff",
    "uv run pip-audit",
    "docker compose ps",
    "docker compose logs",
)


def _is_allowed_command(command: str) -> bool:
    cmd = command.strip()
    return any(cmd == prefix or cmd.startswith(prefix + " ") for prefix in BASH_ALLOWLIST)


async def bash(command: str) -> str:
    # 지연 import: 테스트에서 filesystem.WORKSPACE 패치 시 반영되도록
    from app.tools.filesystem import MAX_FILE_BYTES, WORKSPACE

    if SHELL_METAS.search(command):
        return "실행 거부: 셸 메타문자(;&|`<>$) 포함"
    if not _is_allowed_command(command):
        return f"실행 거부: allowlist 에 없음. 허용 prefix: {', '.join(BASH_ALLOWLIST)}"

    try:
        args = shlex.split(command)
    except ValueError as e:
        return f"명령 파싱 실패: {e}"

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(WORKSPACE),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError as e:
        return f"명령 실행 실패: {e}"

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=BASH_TIMEOUT_S)
    except TimeoutError:
        proc.kill()  # 타임아웃 시 고아 프로세스가 남지 않도록 종료
        await proc.wait()
        return f"실행 타임아웃 {BASH_TIMEOUT_S}s"

    out = stdout.decode("utf-8", errors="replace")
    if len(out) > MAX_FILE_BYTES:
        out = out[:MAX_FILE_BYTES] + "\n...(잘림)"
    return f"exit={proc.returncode}\n{out}"
