from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


GitActionClass = Literal[
    "credential_mutation",
    "destructive_filesystem",
    "git_history_mutation",
    "identity_access_mutation",
]
GitRisk = Literal["high", "critical"]


@dataclass(frozen=True)
class GitAuthority:
    action_class: GitActionClass
    risk: GitRisk
    reason: str
    target_display: str
    confirmation_phrase: str


@dataclass(frozen=True)
class GitInvocation:
    command: str
    arguments: tuple[str, ...]


_GLOBAL_VALUE_OPTIONS = frozenset(
    {
        "-C",
        "-c",
        "--config-env",
        "--exec-path",
        "--git-dir",
        "--namespace",
        "--super-prefix",
        "--work-tree",
    }
)
_GLOBAL_FLAG_OPTIONS = frozenset(
    {
        "--bare",
        "--glob-pathspecs",
        "--help",
        "--html-path",
        "--icase-pathspecs",
        "--info-path",
        "--literal-pathspecs",
        "--man-path",
        "--no-literal-pathspecs",
        "--no-optional-locks",
        "--no-pager",
        "--no-replace-objects",
        "--noglob-pathspecs",
        "--paginate",
        "--version",
    }
)


def _command_word(value: str) -> str:
    word = value.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"\.(?:exe|cmd|bat)$", "", word)


def _parse_invocation(parts: list[str]) -> GitInvocation | None:
    if not parts or _command_word(parts[0]) != "git":
        return None
    index = 1
    while index < len(parts):
        part = parts[index]
        if part == "--":
            index += 1
            break
        if not part.startswith("-") or part == "-":
            break
        if part in _GLOBAL_FLAG_OPTIONS:
            index += 1
            continue
        if part in _GLOBAL_VALUE_OPTIONS:
            if index + 1 >= len(parts):
                return None
            index += 2
            continue
        if part.startswith(("-C", "-c")) and len(part) > 2:
            index += 1
            continue
        if part.startswith("--") and any(
            part.startswith(f"{option}=") for option in _GLOBAL_VALUE_OPTIONS if option.startswith("--")
        ):
            index += 1
            continue
        return None
    if index >= len(parts):
        return GitInvocation("", ())
    return GitInvocation(parts[index].lower(), tuple(parts[index + 1 :]))


def _short_flag(arguments: tuple[str, ...], flag: str) -> bool:
    return any(
        argument.startswith("-")
        and not argument.startswith("--")
        and argument != "-"
        and flag in argument[1:]
        for argument in arguments
    )


def _has(arguments: tuple[str, ...], *options: str) -> bool:
    return any(argument in options for argument in arguments)


def _authority(
    action_class: GitActionClass,
    risk: GitRisk,
    reason: str,
    target: str,
    phrase: str,
) -> GitAuthority:
    return GitAuthority(action_class, risk, reason, target, phrase)


def _history(reason: str, target: str) -> GitAuthority:
    return _authority(
        "git_history_mutation",
        "critical",
        reason,
        target,
        "approve git history mutation",
    )


def _config_is_read_only(arguments: tuple[str, ...]) -> bool:
    read_flags = frozenset(
        {
            "--get",
            "--get-all",
            "--get-color",
            "--get-colorbool",
            "--get-regexp",
            "--get-urlmatch",
            "--list",
            "-l",
        }
    )
    write_flags = frozenset(
        {
            "--add",
            "--edit",
            "--remove-section",
            "--rename-section",
            "--replace-all",
            "--unset",
            "--unset-all",
            "-e",
        }
    )
    scopes = frozenset({"--global", "--local", "--system", "--worktree"})
    value_options = frozenset({"--default", "--file", "--type", "-f", "-t"})
    modifiers = frozenset(
        {
            "--fixed-value",
            "--includes",
            "--name-only",
            "--no-includes",
            "--null",
            "--show-names",
            "--show-origin",
            "--show-scope",
            "-z",
        }
    )
    remaining: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        lowered = argument.lower()
        if lowered in scopes or lowered in modifiers:
            index += 1
            continue
        if lowered in value_options:
            if index + 1 >= len(arguments):
                return True
            index += 2
            continue
        if lowered.startswith("--") and any(
            lowered.startswith(f"{option}=") for option in value_options if option.startswith("--")
        ):
            index += 1
            continue
        remaining.append(lowered)
        index += 1

    if not remaining:
        return True
    if any(argument in write_flags for argument in remaining):
        return False
    if any(argument in read_flags for argument in remaining):
        return True
    modern_action = remaining[0]
    if modern_action in {"get", "get-all", "get-color", "get-colorbool", "get-regexp", "get-urlmatch", "list"}:
        return True
    if modern_action in {"add", "edit", "remove-section", "rename-section", "set", "set-all", "unset", "unset-all"}:
        return False
    positionals = [argument for argument in remaining if not argument.startswith("-")]
    return len(positionals) <= 1


def parse_git_authority(parts: list[str]) -> GitAuthority | None:
    invocation = _parse_invocation(parts)
    if invocation is None or not invocation.command:
        return None
    command = invocation.command
    arguments = invocation.arguments
    lowered = tuple(argument.lower() for argument in arguments)
    target = " ".join(("git", command, *arguments[:2]))

    if command == "clean":
        dry_run = "--dry-run" in lowered or _short_flag(arguments, "n")
        if not dry_run:
            critical = _short_flag(arguments, "d") or _short_flag(arguments, "x") or _short_flag(arguments, "X")
            return _authority(
                "destructive_filesystem",
                "critical" if critical else "high",
                "Git clean can permanently delete untracked worktree files or directories.",
                target,
                "approve git clean",
            )

    if command == "restore":
        return _authority(
            "destructive_filesystem",
            "high",
            "Git restore can discard tracked worktree or staged changes.",
            target,
            "approve git worktree discard",
        )

    if command == "checkout" and ("--" in arguments or "." in arguments):
        return _authority(
            "destructive_filesystem",
            "high",
            "Git checkout can discard tracked worktree changes for selected paths.",
            target,
            "approve git worktree discard",
        )

    if command == "stash" and lowered and lowered[0] in {"clear", "drop", "pop"}:
        return _authority(
            "destructive_filesystem",
            "high",
            "Git stash can delete saved work after clearing, dropping, or applying it.",
            target,
            "approve git stash mutation",
        )

    if command == "worktree" and lowered[:1] == ("remove",):
        worktree_target = next((argument for argument in arguments[1:] if not argument.startswith("-")), "")
        return _authority(
            "destructive_filesystem",
            "critical",
            "Git worktree remove can delete a worktree and its local files.",
            worktree_target or "git worktree",
            f"delete {worktree_target}".lower()[:80] if worktree_target else "approve worktree deletion",
        )

    if command in {"branch", "tag"} and (
        _has(arguments, "--delete") or _short_flag(arguments, "d") or _short_flag(arguments, "D")
    ):
        return _history("Git can delete branch or tag refs.", target)

    if command == "reflog" and lowered[:1] in (("expire",), ("delete",)):
        return _history("Git can remove reflog entries used to recover prior repository state.", target)
    if command == "prune":
        return _history("Git prune can permanently remove unreachable recovery objects.", target)
    if command == "gc" and "--dry-run" not in lowered and any(
        argument == "--prune" or argument.startswith("--prune=") for argument in lowered
    ):
        return _history("Git garbage collection can prune recovery objects.", target)

    if command == "update-ref":
        return _history("Git update-ref can create, move, or delete refs directly.", target)
    if command == "replace" and arguments and lowered[0] not in {"-l", "--list", "list"}:
        return _history("Git replace can create, edit, or delete replacement refs.", target)
    if command == "notes" and lowered and lowered[0] not in {"get-ref", "list", "show"}:
        return _history("Git notes can mutate refs-backed commit metadata.", target)

    if command == "symbolic-ref":
        positionals: list[str] = []
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument in {"-d", "--delete"}:
                return _history("Git symbolic-ref can delete symbolic refs such as HEAD.", target)
            if argument in {"-m", "--message"}:
                index += 2
                continue
            if not argument.startswith("-"):
                positionals.append(argument)
            index += 1
        if len(positionals) >= 2:
            return _history("Git symbolic-ref can repoint symbolic refs such as HEAD.", target)

    if command == "commit" and "--amend" in lowered:
        return _history("Git commit --amend rewrites the current commit.", target)
    if command == "branch" and (_has(arguments, "--force") or _short_flag(arguments, "f")):
        return _history("Git branch force can move an existing branch ref.", target)
    if command in {"checkout", "switch"} and (
        "-B" in arguments or "-C" in arguments or "--force-create" in lowered
    ):
        return _history("Git can force-create or reset a branch ref.", target)
    if command in {"am", "cherry-pick", "merge", "revert"} and "--abort" in lowered:
        return _history("Aborting an in-progress Git operation can reset repository state.", target)
    if command == "lfs" and lowered[:2] in (("migrate", "import"), ("migrate", "export")):
        return _history("Git LFS migrate can rewrite repository history.", target)

    if command in {"filter-branch", "filter-repo", "rebase", "reset"}:
        return _history("Git can rewrite published history or discard local work.", target)
    if "--force-with-lease" in lowered or "--force" in lowered or (
        command in {"push", "tag"} and _short_flag(arguments, "f")
    ):
        return _history("Git force operations can rewrite refs or published history.", target)

    if command == "remote" and lowered[:1] and lowered[0] in {"add", "remove", "rename", "set-url"}:
        return _authority(
            "identity_access_mutation",
            "high",
            "Git remote changes alter routing for future fetch or publish operations.",
            target,
            "approve git remote routing",
        )

    if command == "config" and not _config_is_read_only(arguments):
        return _authority(
            "identity_access_mutation",
            "high",
            "Git config can change identity, credential, hook, or URL-routing configuration.",
            target,
            "approve git config mutation",
        )

    if command == "credential" and lowered[:1] and lowered[0] in {"approve", "fill", "reject"}:
        action = lowered[0]
        return _authority(
            "credential_mutation",
            "critical" if action == "fill" else "high",
            "Git credential plumbing can read, store, or remove helper-managed credentials.",
            target,
            "approve git credential access",
        )

    return None


def decide_git_authority(parts: list[str], context: Any, decision_factory: Callable[..., Any]) -> Any:
    authority = parse_git_authority(parts)
    if authority is None:
        return None
    return decision_factory(
        parts,
        context,
        authority.action_class,
        authority.risk,
        authority.reason,
        target_display=authority.target_display,
        confirmation_phrase=authority.confirmation_phrase,
    )
