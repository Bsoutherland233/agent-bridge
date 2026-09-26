"""Use the bridge's native ACL implementation, not Windows chmod bits."""
import os
from pathlib import Path
from ..platform import platform


def verify_private_directory(path: Path) -> None:
    path = Path(path)
    if os.name == 'nt':
        ok, _ = platform.observe_owner_only_tree(str(path))
        if not ok:
            raise ValueError('Private room storage failed Windows ACL verification')
    else:
        for item in [path, *path.rglob('*')]:
            if item.is_symlink() or item.stat().st_uid != os.getuid() or item.stat().st_mode & 0o077:
                raise ValueError('Private room storage is not owner-only')


def prepare_private_directory(path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == 'nt':
        ok, _ = platform.enforce_owner_only_tree(str(path))
        if not ok:
            raise ValueError('Unable to protect private room storage')
    else:
        os.chmod(path, 0o700)
    verify_private_directory(path)
