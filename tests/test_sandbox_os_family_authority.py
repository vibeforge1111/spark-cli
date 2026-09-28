from __future__ import annotations

from spark_cli.sandbox import access, docker, paths


def test_sandbox_os_family_uses_one_canonical_classifier() -> None:
    assert access.access_os_family is paths.os_family
    assert docker.docker_os_family is paths.os_family


def test_sandbox_os_family_accepts_explicit_platform_values() -> None:
    assert paths.os_family("darwin") == "macos"
    assert paths.os_family("win32") == "windows"
    assert paths.os_family("linux") == "linux"
    assert paths.os_family("freebsd") == "unknown"
