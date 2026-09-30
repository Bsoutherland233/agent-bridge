"""The verification-command policy both bounded harnesses enforce.

One definition, imported by ``claude_task``, ``codex_task`` and the execution
queue's admission check, so that a request the harness would refuse is
refused at submission with the same words, instead of being admitted, run,
and reported as a bare ``TaskError`` twenty seconds later (jobs d8e5763d,
7a79ae7f and 19869b0e in the live queue all failed this way).

The policy is deliberately small: a fixed allowlist of programs named without
a path, Python limited to its two test runners as modules, git limited to
read-only subcommands, and no control characters anywhere in an argument.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import PurePosixPath, PureWindowsPath
from typing import Callable


class VerifyPolicyError(ValueError):
    """A verification command the harnesses will not run. Fixed text."""


ALLOWED_VERIFY_PROGRAMS = frozenset(
    {"git", "pytest", "python", "python3", "npm", "pnpm", "yarn", "cargo", "go"})
PYTHON_PROGRAMS = frozenset({"python", "python3"})
PYTHON_TEST_MODULES = ("pytest", "unittest")
GIT_READ_ONLY = frozenset({"diff", "status"})

MESSAGE_SHAPE = "verification must be JSON argv arrays"
MESSAGE_PROGRAM = "verification executable is not allowlisted"
MESSAGE_PYTHON = "Python verification is limited to python -m pytest or python -m unittest"
MESSAGE_GIT = "git verification is read-only"
MESSAGE_CONTROL = "control character in verification argv"
MESSAGE_NOT_ON_PATH = "verification program is not on the worker's PATH: {}"
MESSAGE_MODULE = "verification module is not importable by the worker's {}: {}"
MESSAGE_PROBE = "could not check the worker's {} for {}"

#: How long one interpreter probe may take before the job is refused.
PROBE_TIMEOUT_SECONDS = 30
_PROBE_UNAVAILABLE = 3


def _bare_name(program: str) -> bool:
    """Whether ``program`` names an executable with no directory on either OS."""
    return (PurePosixPath(program).name == program
            and PureWindowsPath(program).name == program
            and "\\" not in program and "/" not in program)


def check_verify_argv(commands: object) -> list[list[str]]:
    """Return a copy of ``commands`` if every command is permitted, or raise.

    Emptiness is the caller's business: the Claude lane requires at least one
    command and the Codex lane permits none, and both decide that before
    calling here.
    """
    if not isinstance(commands, list):
        raise VerifyPolicyError(MESSAGE_SHAPE)
    for command in commands:
        if (not isinstance(command, list) or not command
                or not all(isinstance(part, str) and part for part in command)):
            raise VerifyPolicyError(MESSAGE_SHAPE)
        program = command[0]
        if not _bare_name(program) or program not in ALLOWED_VERIFY_PROGRAMS:
            raise VerifyPolicyError(MESSAGE_PROGRAM)
        if program in PYTHON_PROGRAMS and (
                len(command) < 3 or command[1] != "-m"
                or command[2] not in PYTHON_TEST_MODULES):
            raise VerifyPolicyError(MESSAGE_PYTHON)
        if program == "git" and (len(command) < 2 or command[1] not in GIT_READ_ONLY):
            raise VerifyPolicyError(MESSAGE_GIT)
        if any(any(char in part for char in ("\0", "\n", "\r")) for part in command):
            raise VerifyPolicyError(MESSAGE_CONTROL)
    return [list(command) for command in commands]


def check_runnable(commands: list[list[str]], path: str, *,
                   run: Callable[..., "subprocess.CompletedProcess[bytes]"] = subprocess.run,
                   which: Callable[..., str | None] = shutil.which) -> None:
    """Refuse a job whose verification cannot start on this worker.

    Called by the execution worker before it spends a provider run: 5 of the
    first 39 live jobs generated for 6 to 23 minutes and then failed because
    the worker's PATH had no ``python`` or ``pytest``, or its ``python3`` had
    no pytest module. ``commands`` has already passed ``check_verify_argv``,
    so every program is a bare allowlisted name and safe to name in a reason.

    Only what the verify step would do is checked, with the environment the
    harness gives it: ``path`` is the worker's PATH, and the interpreter probe
    runs isolated (``-I``) with a throwaway HOME, as the sandboxed verify step
    has no user site-packages either. git is resolved by the harness itself,
    not from PATH, and is not checked here. unittest ships with Python.
    Anything the check cannot establish is a refusal, never a pass.
    """
    for command in commands:
        program = command[0]
        if program == "git":
            continue
        resolved = which(program, path=path)
        if not resolved:
            raise VerifyPolicyError(MESSAGE_NOT_ON_PATH.format(program))
        if program in PYTHON_PROGRAMS and command[2] == "pytest":
            code = ("import importlib.util, sys; "
                    f"sys.exit(0 if importlib.util.find_spec('pytest') else {_PROBE_UNAVAILABLE})")
            with tempfile.TemporaryDirectory(prefix="verify-probe-") as home:
                try:
                    result = run([resolved, "-I", "-c", code], env={
                        "PATH": path, "HOME": home, "LANG": "C.UTF-8"},
                        cwd=home, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=PROBE_TIMEOUT_SECONDS,
                        check=False)
                except (OSError, subprocess.SubprocessError):
                    raise VerifyPolicyError(MESSAGE_PROBE.format(program, "pytest")) from None
            if result.returncode == _PROBE_UNAVAILABLE:
                raise VerifyPolicyError(MESSAGE_MODULE.format(program, "pytest"))
            if result.returncode != 0:
                raise VerifyPolicyError(MESSAGE_PROBE.format(program, "pytest"))
