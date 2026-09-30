"""Real bridge adapter. Readiness requires full configuration-bound canaries."""
from pathlib import Path
from .. import broker, health, setup_cmd, store


class BridgeAdapter:
    def __init__(self, cfg, target: str, evidence: Path):
        if target not in ('claude', 'codex'):
            raise ValueError('Unsupported bridge target')
        self.cfg, self.target, self.evidence = cfg, target, evidence
        self.caller = 'codex' if target == 'claude' else 'claude'
        self.timeout = cfg.request_timeout(target) + 15

    def status(self) -> dict:
        try:
            setup_cmd.validate_promotion(self.cfg, store.read_json(str(self.evidence)))
        except (OSError, ValueError, KeyError, TypeError):
            return {'state': 'verification_required', 'detail': 'Bridge setup and full live verification are required before this agent can reply.'}
        try:
            report = health.inspect_peer(self.cfg, self.target)
            if report.get('auth', {}).get('state') != 'signed_in':
                return {'state': 'login_required', 'detail': 'Sign in to the bridge provider profile.'}
        except Exception:
            return {'state': 'failed', 'detail': 'Provider preflight failed. Check bridge setup.'}
        return {'state': 'ready'}

    def _admit(self):
        state = self.status()
        if state['state'] != 'ready':
            raise ValueError(state['detail'])

    def _check_local_first(self, prompt: str):
        if self.cfg.local_first_enabled() and len(prompt.encode('utf-8')) >= self.cfg.local_first_min_bytes():
            raise ValueError('Prompt is above the local_first limit; prepare a local digest before peer dispatch')

    def start(self, prompt: str, classification: str) -> dict:
        self._check_local_first(prompt)
        self._admit()
        return broker.start(self.cfg, self.caller, {'prompt': prompt, 'source_classification': classification})

    def continue_(self, conversation_id: str, prompt: str, classification: str) -> dict:
        self._check_local_first(prompt)
        self._admit()
        return broker.continue_(self.cfg, self.caller, {'conversation_id': conversation_id, 'prompt': prompt, 'source_classification': classification})

    def poll(self, job_id: str) -> dict:
        return broker.poll(self.cfg, self.caller, {'job_id': job_id})

    def read(self, job_id: str) -> dict:
        return broker.read(self.cfg, self.caller, {'job_id': job_id})
