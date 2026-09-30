"""The worker refuses a job whose verification cannot start, before any run.

Offline. Fake programs live in a temporary PATH; the only real interpreter
used is the one running these tests.
"""

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_bridge.execution.verify_policy import VerifyPolicyError, check_runnable
from agent_bridge.orchestration.execution_queue import (
    ExecutionAdmissionError, Harnesses, SubprocessHarnessExecutor)


def _program(directory, name, exit_code=0):
    path = Path(directory) / name
    path.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@unittest.skipIf(os.name != "posix", "fake programs are shell scripts")
class CheckRunnableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bin = self.temp.name

    def tearDown(self):
        self.temp.cleanup()

    def test_a_program_missing_from_the_worker_path_is_refused_by_name(self):
        # Live jobs c0849b26, beffeccc, 7dcda0b7: execvp of pytest/python failed.
        for command in (["pytest", "-q"], ["python", "-m", "pytest"], ["npm", "test"]):
            with self.subTest(command=command):
                with self.assertRaisesRegex(VerifyPolicyError,
                                            f"not on the worker's PATH: {command[0]}$"):
                    check_runnable([command], self.bin)

    def test_runnable_commands_pass(self):
        _program(self.bin, "python3")
        _program(self.bin, "pytest")
        check_runnable([["python3", "-m", "pytest", "-q"], ["pytest"],
                        ["python3", "-m", "unittest", "discover"], ["git", "status"]],
                       self.bin)

    def test_git_is_not_looked_up(self):
        check_runnable([["git", "diff"]], self.bin)

    def test_nothing_is_executed(self):
        _program(self.bin, "python3", exit_code=3)
        with mock.patch.object(subprocess, "run") as run, \
                mock.patch.object(subprocess, "Popen") as popen:
            check_runnable([["python3", "-m", "pytest"]], self.bin)
        run.assert_not_called()
        popen.assert_not_called()

    def test_relative_and_empty_path_entries_do_not_count(self):
        # The verifier and the worker have different working directories.
        os.makedirs(os.path.join(self.bin, "rel"))
        _program(os.path.join(self.bin, "rel"), "pytest")
        previous = os.getcwd()
        os.chdir(self.bin)
        try:
            for path in ("rel", "", os.pathsep + "rel"):
                with self.subTest(path=path):
                    with self.assertRaisesRegex(VerifyPolicyError, "not on the worker's PATH"):
                        check_runnable([["pytest"]], path)
        finally:
            os.chdir(previous)


@unittest.skipIf(os.name != "posix", "the execution worker is POSIX only")
class ExecutorRefusesBeforeSpawningTests(unittest.TestCase):
    def test_an_unrunnable_verify_command_never_starts_the_harness(self):
        with tempfile.TemporaryDirectory() as empty:
            executor = SubprocessHarnessExecutor(Harnesses(
                codex=ROOT / "src" / "agent_bridge" / "execution" / "codex_task.py",
                claude=ROOT / "src" / "agent_bridge" / "execution" / "claude_task.py",
                python=Path(sys.executable), claude_config_dir=None))
            request = {"provider": "codex", "brief": "/tmp/brief", "repo": "/tmp/repo",
                       "base": "HEAD", "timeout_seconds": 60, "classification": "synthetic",
                       "model": "m", "effort": "low", "verify_argv": [["pytest", "-q"]]}
            with mock.patch.dict(os.environ, {"PATH": empty}), \
                    mock.patch.object(subprocess, "Popen") as popen:
                with self.assertRaises(ExecutionAdmissionError) as caught:
                    executor(request, Path(empty))
            popen.assert_not_called()
            self.assertEqual(str(caught.exception),
                             "verify_not_runnable: verification program is not on "
                             "the worker's PATH: pytest")


if __name__ == "__main__":
    unittest.main()
