"""Room policy preserves the bridge's client-data refusal."""
from pathlib import Path
from ..config import Config
from .storage import LABELS
from .windows_security import verify_private_directory


class RoomPolicy:
    def __init__(self, allow_client: bool = False):
        if allow_client:
            raise ValueError('Client-derived material is not supported')
        self.allow_client = False

    def effective_classification(self, labels: list[str]) -> str:
        if any(label not in LABELS for label in labels):
            raise ValueError('Client material, credentials and secrets cannot be shared')
        return next((label for label in ('internal', 'synthetic') if label in labels), 'public')

    def authorize(self, target: str, classification: str) -> None:
        if target not in ('claude', 'codex', 'hermes', 'grok'):
            raise ValueError('Unknown peer')
        if classification not in LABELS:
            raise ValueError('Room policy refuses this classification')


def room_config(cfg: Config, policy: RoomPolicy) -> Config:
    verify_private_directory(Path(cfg.state_root))
    return cfg
