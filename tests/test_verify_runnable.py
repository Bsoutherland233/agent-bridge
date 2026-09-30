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

from agent_bridge.execution import verify_policy
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

    def test_an_interpreter_without_pytest_is_refused(self):
        # Live jobs 9e66f13c, 2039124c: "No module named pytest".
        _program(self.bin, "python3", exit_code=3)
        with self.assertRaisesRegex(VerifyPolicyError,
                                    "not importable by the worker's python3: pytest"):
            check_runnable([["python3", "-m", "pytest", "-q"]], self.bin)

    def test_a_probe_that_cannot_answer_is_a_refusal_not_a_pass(self):
        _program(self.bin, "python3", exit_code=1)
        with self.assertRaisesRegex(VerifyPolicyError, "could not check"):
            check_runnable([["python3", "-m", "pytest"]], self.bin)
        _program(self.bin, "python3", exit_code=0)
        with self.assertRaisesRegex(VerifyPolicyError, "could not check"):
            check_runnable([["python3", "-m", "pytest"]], self.bin, run=mock.Mock(
                side_effect=subprocess.TimeoutExpired("python3", 30)))

    def test_runnable_commands_pass(self):
        _program(self.bin, "python3", exit_code=0)
        _program(self.bin, "pytest")
        check_runnable([["python3", "-m", "pytest", "-q"], ["pytest"],
                        ["python3", "-m", "unittest", "discover"], ["git", "status"]],
                       self.bin)

    def test_unittest_and_git_are_not_probed(self):
        _program(self.bin, "python3", exit_code=3)
        run = mock.Mock()
        check_runnable([["python3", "-m", "unittest"], ["git", "diff"]], self.bin, run=run)
        run.assert_not_called()

    def test_the_probe_runs_isolated_with_a_throwaway_home(self):
        _program(self.bin, "python3", exit_code=0)
        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0))
        check_runnable([["python3", "-m", "pytest"]], self.bin, run=run)
        argv, kwargs = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual(argv[1:3], ["-I", "-c"])
        self.assertEqual(kwargs["env"]["PATH"], self.bin)
        self.assertNotEqual(kwargs["env"]["HOME"], str(Path.home()))
        self.assertNotIn("PYTHONPATH", kwargs["env"])

    def test_the_real_interpreter_probe_agrees_with_an_import(self):
        directory = os.path.dirname(os.path.realpath(sys.executable))
        name = os.path.basename(os.path.realpath(sys.executable))
        if name not in ("python", "python3"):
            os.symlink(os.path.realpath(sys.executable), os.path.join(self.bin, "python3"))
            directory, name = self.bin, "python3"
        has_pytest = subprocess.run(
            [os.path.join(directory, name), "-I", "-c", "import pytest"],
            capture_output=True, env={"PATH": directory, "HOME": self.bin}).returncode == 0
        try:
            check_runnable([[name, "-m", "pytest"]], directory)
            refused = False
        except VerifyPolicyError:
            refused = True
        self.assertEqual(refused, not has_pytest)


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
