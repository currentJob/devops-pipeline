"""PoC compose 정적 보안 검사 — 호스트 탈출 directive 차단 검증 (보안 핵심)."""

from __future__ import annotations

from app.pocsandbox.checks import find_violations


def _cfg(svc: dict, name: str = "app") -> dict:
    return {"services": {name: svc}}


def test_clean_passes():
    cfg = _cfg(
        {
            "image": "python:3.12-slim",
            "build": {"context": "/work/poc/demo/app"},
            "volumes": [{"type": "volume", "source": "data", "target": "/data"}],
            "networks": {"internal": None},
        }
    )
    assert find_violations(cfg, poc_root="/work/poc/demo") == []


def test_privileged_blocked():
    assert "privileged 금지" in "; ".join(find_violations(_cfg({"privileged": True})))


def test_host_bind_blocked():
    cfg = _cfg({"volumes": [{"type": "bind", "source": "/etc", "target": "/etc"}]})
    assert any("host bind" in v for v in find_violations(cfg))


def test_host_bind_string_form_blocked():
    cfg = _cfg({"volumes": ["/var/run:/var/run"]})
    assert any("host bind" in v for v in find_violations(cfg))


def test_docker_sock_blocked():
    cfg = _cfg({"volumes": [{"type": "bind", "source": "/var/run/docker.sock", "target": "/x"}]})
    assert any("docker.sock" in v for v in find_violations(cfg))


def test_network_mode_host_blocked():
    assert any("network_mode" in v for v in find_violations(_cfg({"network_mode": "host"})))


def test_network_mode_container_blocked():
    cfg = _cfg({"network_mode": "container:other"})
    assert any("network_mode" in v for v in find_violations(cfg))


def test_cap_add_blocked():
    assert any("cap_add" in v for v in find_violations(_cfg({"cap_add": ["SYS_ADMIN"]})))


def test_devices_blocked():
    assert any("devices" in v for v in find_violations(_cfg({"devices": ["/dev/sda:/dev/sda"]})))


def test_pid_host_blocked():
    assert any("pid host" in v for v in find_violations(_cfg({"pid": "host"})))


def test_build_context_escape_blocked():
    cfg = _cfg({"build": {"context": "/etc"}})
    assert any("컨텍스트" in v for v in find_violations(cfg, poc_root="/work/poc/demo"))


def test_named_volume_with_host_device_blocked():
    cfg = {
        "services": {"app": {"image": "x"}},
        "volumes": {"v": {"driver_opts": {"type": "none", "device": "/host/path", "o": "bind"}}},
    }
    assert any("host bind 볼륨" in v for v in find_violations(cfg))
