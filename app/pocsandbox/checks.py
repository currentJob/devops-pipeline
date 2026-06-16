"""PoC compose 정적 보안 검사 (보안 핵심 — 호스트 탈출 directive 차단).

입력: `docker compose config --format json` 의 파싱 결과(dict). 실행 전 이 검사를 통과해야
build/run 으로 넘어간다. 순수 함수라 단위 테스트로 검증한다.
"""

from __future__ import annotations

import posixpath

# 컨테이너 탈출/호스트 접근에 쓰일 수 있는 위험 요소
_HOST_NETWORK_MODES = {"host"}


def _is_host_bind(mount: dict | str) -> bool:
    """호스트 경로 bind 마운트 여부 (명명 볼륨은 허용)."""
    if isinstance(mount, str):
        # "src:dst[:opts]" — src 가 경로(/, ., ~)면 host bind
        src = mount.split(":", 1)[0]
        return src.startswith(("/", ".", "~"))
    return mount.get("type") == "bind"


def _mount_source(mount: dict | str) -> str:
    if isinstance(mount, str):
        return mount.split(":", 1)[0]
    return str(mount.get("source", ""))


def _under(path: str, root: str) -> bool:
    """path 가 root 하위(또는 동일)인지 — 경로 탈출 검사."""
    if not root:
        return True
    np = posixpath.normpath(path)
    nr = posixpath.normpath(root)
    return np == nr or np.startswith(nr + "/")


def find_violations(config: dict, poc_root: str = "") -> list[str]:
    """compose config(dict) 에서 보안 위반 목록 반환 (빈 리스트 = 통과).

    거부: privileged, host bind 마운트, docker.sock, network_mode host/container,
          cap_add, devices, pid/ipc/userns host, 빌드 컨텍스트 경로 탈출.
    """
    violations: list[str] = []
    services = config.get("services") or {}

    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue

        if svc.get("privileged"):
            violations.append(f"{name}: privileged 금지")

        for mount in svc.get("volumes") or []:
            src = _mount_source(mount)
            if "docker.sock" in src:
                violations.append(f"{name}: docker.sock 마운트 금지")
            elif _is_host_bind(mount):
                violations.append(f"{name}: host bind 마운트 금지 ({src or '?'})")

        nm = svc.get("network_mode")
        if isinstance(nm, str) and (nm in _HOST_NETWORK_MODES or nm.startswith("container:")):
            violations.append(f"{name}: network_mode {nm!r} 금지")

        if svc.get("cap_add"):
            violations.append(f"{name}: cap_add 금지 ({svc['cap_add']})")
        if svc.get("devices"):
            violations.append(f"{name}: devices 금지")
        for key in ("pid", "ipc", "userns_mode"):
            if svc.get(key) == "host":
                violations.append(f"{name}: {key} host 금지")

        build = svc.get("build")
        ctx = build.get("context") if isinstance(build, dict) else build
        if isinstance(ctx, str) and poc_root and not _under(ctx, poc_root):
            violations.append(f"{name}: 빌드 컨텍스트가 PoC 경로 밖 ({ctx})")

    # 최상위 명명 볼륨이 host bind(driver_opts device=경로)면 거부
    for vname, vol in (config.get("volumes") or {}).items():
        if isinstance(vol, dict):
            opts = vol.get("driver_opts") or {}
            if str(opts.get("type")) == "none" or "device" in opts:
                violations.append(f"volume {vname}: host bind 볼륨 금지")

    return violations
