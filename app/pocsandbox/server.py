"""PoC 격리 실행 사이드카 — stdlib HTTP + docker 오케스트레이션.

POST /run {"slug": "..."} :
  1. slug 검증 → prompts/output/poc/<slug>/ (traversal 차단)
  2. docker compose config --format json → 정적 보안 검사(checks)
  3. build (네트워크 필요) → 단일 서비스 격리 실행(--network none, 자원캡)
  4. finally: down -v + rm -f (자동 teardown)
반환: {"ok", "stage", "logs"}

docker.sock 은 이 컨테이너에만 마운트된다. 외부(bot)에서만 호출(내부 네트워크).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app.pocsandbox.checks import find_violations

POC_ROOT = Path(os.environ.get("POC_ROOT", "/poc"))
HOST = "0.0.0.0"
PORT = int(os.environ.get("POCSANDBOX_PORT", "8770"))

BUILD_TIMEOUT = 300  # 빌드(네트워크 필요)
RUN_TIMEOUT = 60  # 단일 실행
TEARDOWN_TIMEOUT = 60
MEM = "512m"
CPUS = "1.0"
PIDS = "256"
LOG_MAX = 6000
_PRIMARY = ("app", "api", "main", "web", "server", "worker")
_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def _run(cmd: list[str], timeout: int) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"(타임아웃 {timeout}s)"
    except OSError as e:
        return 1, f"(실행 실패: {e})"


def _trim(text: str) -> str:
    return text if len(text) <= LOG_MAX else text[:LOG_MAX] + "\n...(로그 잘림)"


def _pick_image(images_out: str) -> tuple[str | None, str | None]:
    """`compose images --format json` 출력 → (service, image)."""
    rows: list[dict] = []
    try:
        data = json.loads(images_out)
        rows = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        for line in images_out.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    if not rows:
        return None, None

    def _img(r: dict) -> str:
        repo, tag = r.get("Repository", ""), r.get("Tag", "")
        return f"{repo}:{tag}" if repo and tag else (r.get("ID") or "")

    by_service = {r.get("Service", ""): r for r in rows}
    for name in _PRIMARY:
        if name in by_service and _img(by_service[name]):
            return name, _img(by_service[name])
    first = rows[0]
    return first.get("Service"), _img(first)


def run_poc(slug: str) -> dict:
    """검증 → 정적검사 → build → 격리 단일 실행 → teardown."""
    if not _SLUG_RE.fullmatch(slug or ""):
        return {"ok": False, "stage": "slug", "logs": f"잘못된 slug: {slug!r}"}

    poc_dir = (POC_ROOT / slug).resolve()
    if not str(poc_dir).startswith(str(POC_ROOT.resolve())):
        return {"ok": False, "stage": "slug", "logs": "경로 탈출 거부"}
    compose = poc_dir / "docker-compose.yml"
    if not compose.is_file():
        return {"ok": False, "stage": "slug", "logs": f"docker-compose.yml 없음: {slug}"}

    project = f"pocrun-{re.sub(r'[^a-z0-9-]', '-', slug)}"
    base = ["docker", "compose", "-f", str(compose), "-p", project]
    run_name = f"{project}-run"

    try:
        rc, out = _run([*base, "config", "--format", "json"], 30)
        if rc != 0:
            return {"ok": False, "stage": "config", "logs": _trim(out)}
        try:
            cfg = json.loads(out)
        except json.JSONDecodeError as e:
            return {"ok": False, "stage": "config", "logs": f"compose config 파싱 실패: {e}"}

        violations = find_violations(cfg, poc_root=str(poc_dir))
        if violations:
            return {
                "ok": False,
                "stage": "check",
                "logs": "정적 검사 위반:\n- " + "\n- ".join(violations),
            }

        rc, build_out = _run([*base, "build"], BUILD_TIMEOUT)
        if rc != 0:
            return {"ok": False, "stage": "build", "logs": _trim(build_out)}

        _, imgs = _run([*base, "images", "--format", "json"], 30)
        service, image = _pick_image(imgs)
        if not image:
            return {
                "ok": True,
                "stage": "build",
                "logs": _trim(build_out + "\n\n(이미지 식별 실패 — build 만 수행, 실행 생략)"),
            }

        rc, run_out = _run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--memory",
                MEM,
                "--cpus",
                CPUS,
                "--pids-limit",
                PIDS,
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--name",
                run_name,
                image,
            ],
            RUN_TIMEOUT,
        )
        if rc == 124:
            _run(["docker", "rm", "-f", run_name], 10)
        header = f"[build OK] [run: {service} ({image}), --network none, mem {MEM}/cpu {CPUS}]\n"
        return {"ok": rc == 0, "stage": "run", "logs": _trim(header + run_out)}
    finally:
        _run([*base, "down", "-v", "--remove-orphans"], TEARDOWN_TIMEOUT)
        _run(["docker", "rm", "-f", run_name], 10)


class _Handler(BaseHTTPRequestHandler):
    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json({"ok": True})
        else:
            self._json({"ok": False, "logs": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/run":
            self._json({"ok": False, "logs": "not found"}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            slug = str(body.get("slug", "")).strip()
        except (ValueError, json.JSONDecodeError):
            self._json({"ok": False, "stage": "request", "logs": "invalid json"}, status=400)
            return
        self._json(run_poc(slug))

    def log_message(self, *_args) -> None:  # 기본 stderr 액세스 로그 억제
        pass


def main() -> None:
    print(f"pocsandbox listening on {HOST}:{PORT} (POC_ROOT={POC_ROOT})", flush=True)
    HTTPServer((HOST, PORT), _Handler).serve_forever()


if __name__ == "__main__":
    main()
