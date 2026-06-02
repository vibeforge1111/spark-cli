"""
Tests for git URL validation hardening (PR #164).

Covers:
1. normalize_git_url() input validation:
   - rejects empty / whitespace-only sources
   - rejects sources starting with '-' (flag injection)
   - allows legitimate https/ssh URLs and hosted-shorthand
   - does not produce false positives on URLs containing '-' mid-string
2. argv hardening at every call site that runs `git` against an
   attacker-controllable URL:
   - clone_module_source() passes '--' before the URL on `git clone`
   - resolve_remote_git_ref() passes '--' before the URL on `git ls-remote`

These two layers (input validation + '--' separator) are belt-and-suspenders:
either alone closes the regression, but together they remain safe even on
older git versions (< 2.30) where '--' handling was inconsistent and even if
a future refactor accidentally reintroduces the missing separator on one
call site.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from spark_cli import cli
from spark_cli.cli import normalize_git_url


class NormalizeGitUrlInputValidationTests(unittest.TestCase):
    """Input boundary checks on normalize_git_url()."""

    def test_empty_source_rejected(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            normalize_git_url("")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_whitespace_only_source_rejected(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            normalize_git_url("   \t  ")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_dash_prefix_long_flag_rejected(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            normalize_git_url("--upload-pack=evil.sh")
        self.assertIn("flag injection", str(ctx.exception).lower())

    def test_dash_prefix_short_flag_rejected(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            normalize_git_url("-c")
        self.assertIn("flag injection", str(ctx.exception).lower())

    def test_https_url_passes_through(self) -> None:
        self.assertEqual(
            normalize_git_url("https://github.com/foo/bar"),
            "https://github.com/foo/bar",
        )

    def test_http_url_passes_through(self) -> None:
        self.assertEqual(
            normalize_git_url("http://example.com/foo/bar"),
            "http://example.com/foo/bar",
        )

    def test_ssh_scp_form_passes_through(self) -> None:
        self.assertEqual(
            normalize_git_url("git@github.com:foo/bar.git"),
            "git@github.com:foo/bar.git",
        )

    def test_hosted_shorthand_normalizes_to_https(self) -> None:
        self.assertEqual(
            normalize_git_url("github.com/foo/bar"),
            "https://github.com/foo/bar",
        )

    def test_url_with_mid_string_dash_is_not_a_false_positive(self) -> None:
        # Mid-string '-' must not trigger the flag-injection guard.
        self.assertEqual(
            normalize_git_url("https://github.com/foo/bar-baz"),
            "https://github.com/foo/bar-baz",
        )

    def test_leading_and_trailing_whitespace_is_stripped(self) -> None:
        self.assertEqual(
            normalize_git_url("  https://github.com/foo/bar  "),
            "https://github.com/foo/bar",
        )


class GitArgvSeparatorTests(unittest.TestCase):
    """
    Verify every call site that invokes git with an attacker-controllable
    URL passes '--' before the URL, so even on older git the URL cannot be
    reinterpreted as a flag.
    """

    def _capture_git_command_argv(self, fn, *args, **kwargs) -> list[list[str]]:
        captured: list[list[str]] = []
        real = cli.git_command

        def spy(*a):
            out = real(*a)
            captured.append(list(out))
            return out

        # Best-effort short-circuit: stop after argv is captured by raising,
        # so we don't need a fully working subprocess pipeline in tests.
        class _Stop(Exception):
            pass

        def fake_run(*a, **kw):
            raise _Stop()

        with patch.object(cli, "git_command", spy), patch.object(
            cli.subprocess, "run", fake_run
        ):
            try:
                fn(*args, **kwargs)
            except _Stop:
                pass
            except SystemExit:
                # surface validation errors; not a test failure here
                raise
            except Exception:
                # Downstream parsing of fake output is fine to swallow; we
                # only care about the argv shape.
                pass
        return captured

    def _argv_for(self, captured: list[list[str]], git_subcmd: str) -> list[str]:
        for cmd in captured:
            if git_subcmd in cmd:
                return cmd
        self.fail(f"no {git_subcmd!r} argv was constructed; captured={captured}")

    def test_clone_uses_double_dash_separator(self) -> None:
        captured = self._capture_git_command_argv(
            cli.clone_module_source,
            name="example",
            source="https://github.com/foo/bar",
        )
        argv = self._argv_for(captured, "clone")
        self.assertIn("--", argv, f"git clone missing '--' separator: {argv}")
        sep_idx = argv.index("--")
        self.assertEqual(
            argv[sep_idx + 1],
            "https://github.com/foo/bar",
            f"URL must be the positional immediately after '--': {argv}",
        )

    def test_ls_remote_uses_double_dash_separator(self) -> None:
        captured = self._capture_git_command_argv(
            cli.resolve_remote_git_ref,
            "https://github.com/foo/bar",
        )
        argv = self._argv_for(captured, "ls-remote")
        self.assertIn("--", argv, f"git ls-remote missing '--' separator: {argv}")
        sep_idx = argv.index("--")
        self.assertEqual(
            argv[sep_idx + 1],
            "https://github.com/foo/bar",
            f"URL must be the positional immediately after '--': {argv}",
        )


class FlagInjectionEndToEndGuardTests(unittest.TestCase):
    """
    Even if a future regression silently drops the '--' separator on either
    call site, normalize_git_url() must continue to reject flag-shaped URLs
    at the boundary.
    """

    def test_clone_path_rejects_flag_url_at_boundary(self) -> None:
        with self.assertRaises(SystemExit):
            cli.clone_module_source(
                name="example",
                source="--upload-pack=evil.sh",
            )

    def test_ls_remote_path_rejects_flag_url_at_boundary(self) -> None:
        with self.assertRaises(SystemExit):
            cli.resolve_remote_git_ref("--upload-pack=evil.sh")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
