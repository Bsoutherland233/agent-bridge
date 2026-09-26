"""Default-profile Hermes consultations through its supported JSONL CLI.

Hermes is an optional third-party provider. The room only starts it when the
operator explicitly supplies the installed CLI path and has completed the
local verification record for that installation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from .. import store
from .windows_security import prepare_private_directory, verify_private_directory


_ENVIRONMENT_KEYS = (
    'PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'TEMP', 'TMP',
    'LANG', 'LC_ALL', 'LC_CTYPE', 'PYTHONIOENCODING', 'PYTHONUTF8',
)


def child_environment(source=None) -> dict[str, str]:
    """Return the small, explicit environment Hermes needs to start."""
    source = os.environ if source is None else source
    return {key: source[key] for key in _ENVIRONMENT_KEYS if key in source}


def decode_result(output: str, returncode: int) -> tuple[str, str]:
    events = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
            if isinstance(event, dict) and event.get('type') == 'result':
                events.append(event)
        except ValueError:
            continue
    if returncode != 0 or len(events) != 1 or events[0].get('exit_code') != 0:
        raise ValueError('Hermes did not return a successful final response. Check its default-profile login.')
    event = events[0]
    if not isinstance(event.get('text'), str) or not event['text'].strip() or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', str(event.get('session_id', ''))):
        raise ValueError('Hermes returned an incomplete response or invalid session ID')
    return event['text'], event['session_id']


class HermesAdapter:
    timeout = 135

    def __init__(self, executable: Path, root: Path, policy):
        self.executable, self.root, self.policy = executable, root, policy
        prepare_private_directory(root)

    def fingerprint(self):
        files = [self.executable]
        source = self.executable.parent.parent / 'hermes-agent' / 'hermes_cli'
        implementation = [source / name for name in ('main.py', 'stream_json.py', 'cli_init_mixin.py')]
        if not all(path.is_file() for path in implementation):
            raise ValueError('Hermes implementation cannot be verified for this installation layout')
        files += implementation
        digest = hashlib.sha256()
        for file in files:
            digest.update(file.read_bytes())
        return digest.hexdigest()

    def status(self) -> dict:
        try:
            evidence = json.loads((self.root / 'verification.json').read_text(encoding='utf-8'))
            if (evidence.get('fingerprint') != self.fingerprint() or evidence.get('profile') != 'default'
                    or evidence.get('start_pass') is not True or evidence.get('resume_pass') is not True
                    or evidence.get('selected_pass') is not True):
                raise ValueError('Unverified')
            verify_private_directory(self.root)
        except (OSError, ValueError):
            return {'state': 'verification_required', 'detail': 'Default Hermes profile needs implementation-bound start, follow-up, and selected-context verification. Unsupported installation layouts remain disconnected.'}
        return {'state': 'ready', 'detail': 'Default Hermes profile; room sessions support clarification only, not filesystem or messaging tools.'}

    def _call(self, prompt, classification, session=None, *, selected_only=False):
        if self.status()['state'] != 'ready':
            raise ValueError('Hermes verification is required')
        self.policy.authorize('hermes', classification)
        if not isinstance(prompt, str) or not 0 < len(prompt) <= 16000:
            raise ValueError('Hermes room context exceeds its 16000-character limit')
        if session and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', session):
            raise ValueError('Invalid Hermes session')
        job_id = str(uuid.uuid4())
        job = self.root / job_id
        prepare_private_directory(job)
        argv = [str(self.executable), '--profile', 'default', 'chat', '--query-file', '-', '--oneshot',
                '--format', 'stream-json', '--toolsets', 'clarify', '--max-turns', '1', '--run-budget', '90', '--source', 'agent-room']
        if selected_only:
            argv.append('--ignore-rules')
        if session:
            argv += ['--resume', session, '--no-restore-cwd']
        try:
            with (job / 'stdout.jsonl').open('w', encoding='utf-8') as out, (job / 'stderr.log').open('w', encoding='utf-8') as err:
                result = subprocess.run(argv, input=prompt, text=True, encoding='utf-8', errors='replace', shell=False,
                                        stdout=out, stderr=err, cwd=job, timeout=120,
                                        env=child_environment(),
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            output = job / 'stdout.jsonl'
            if output.stat().st_size > 4_000_000:
                raise ValueError('Hermes response exceeded the room output limit')
            text, session_id = decode_result(output.read_text(encoding='utf-8'), result.returncode)
        except subprocess.TimeoutExpired:
            raise ValueError('Hermes timed out; its provider call may still consume usage') from None
        store.atomic_write_json(str(job / 'result.json'), {'ok': True, 'peer_response': text})
        return {'ok': True, 'job_id': job_id, 'conversation_id': session_id}

    def start(self, prompt: str, classification: str) -> dict:
        return self._call(prompt, classification)

    def start_selected(self, prompt: str, classification: str) -> dict:
        return self._call(prompt, classification, selected_only=True)

    def continue_(self, conversation_id: str, prompt: str, classification: str) -> dict:
        return self._call(prompt, classification, conversation_id)

    def poll(self, job_id: str) -> dict:
        uuid.UUID(job_id)
        return {'ok': True, 'status': 'complete'}

    def read(self, job_id: str) -> dict:
        if str(uuid.UUID(job_id)) != job_id:
            raise ValueError('Invalid job ID')
        return json.loads((self.root / job_id / 'result.json').read_text(encoding='utf-8'))
