import json
import io
import subprocess
from pathlib import Path
from unittest.mock import patch

from test_peer_rounds import RoundTests
from agent_bridge.chat.hermes import HermesAdapter
from agent_bridge.chat.policy import RoomPolicy


class SelectedHermesTests(RoundTests):
    def test_selected_context_disables_default_profile_memory_and_rules(self):
        adapter = HermesAdapter(Path(self.tmp.name) / 'hermes.exe', Path(self.tmp.name) / 'hermes', RoomPolicy(False))

        class FakeProcess:
            pid = 123
            def __init__(self, output=b''):
                self.stdin = io.BytesIO()
                self.stdout = io.BytesIO(output)
                self.stderr = io.BytesIO()
            def wait(self, timeout=None):
                return 0
            def poll(self):
                return 0

        def fake_popen(argv, **kwargs):
            self.assertIn('--ignore-rules', argv)
            self.assertNotIn('--resume', argv)
            self.assertEqual(argv[argv.index('--profile') + 1], 'default')
            self.assertEqual(argv[argv.index('--toolsets') + 1], 'clarify')
            self.assertFalse(kwargs['shell'])
            self.assertTrue(kwargs['start_new_session'] or kwargs['creationflags'])
            return FakeProcess((json.dumps({'type': 'result', 'exit_code': 0, 'text': 'answer', 'session_id': 'fixture'}) + '\n').encode())

        with patch.object(adapter, 'status', return_value={'state': 'ready'}), patch('agent_bridge.chat.hermes.subprocess.Popen', side_effect=fake_popen):
            result = adapter.start_selected('chosen context', 'synthetic')
        self.assertTrue(result['ok'])
        self.assertTrue((adapter.root / result['job_id'] / 'result.json').exists())
        self.assertEqual(adapter.read(result['job_id'])['peer_response'], 'answer')
        self.assertFalse((adapter.root / result['job_id']).exists())

    def test_large_stderr_is_rejected_before_retention(self):
        adapter = HermesAdapter(Path(self.tmp.name) / 'hermes.exe', Path(self.tmp.name) / 'hermes', RoomPolicy(False))
        class Huge:
            pid = 456
            def __init__(self):
                self.stdin, self.stdout = io.BytesIO(), io.BytesIO(b'{}\n')
                self.stderr = io.BytesIO(b'x' * 1_000_001)
            def wait(self, timeout=None): return 0
            def poll(self): return 0
        with patch.object(adapter, 'status', return_value={'state': 'ready'}), patch('agent_bridge.chat.hermes.subprocess.Popen', return_value=Huge()):
            with self.assertRaises(ValueError): adapter.start('chosen context', 'synthetic')
        self.assertEqual(list(adapter.root.iterdir()), [])
