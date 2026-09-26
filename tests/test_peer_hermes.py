import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from test_peer_rounds import RoundTests
from agent_bridge.chat.hermes import HermesAdapter
from agent_bridge.chat.policy import RoomPolicy


class SelectedHermesTests(RoundTests):
    def test_selected_context_disables_default_profile_memory_and_rules(self):
        adapter = HermesAdapter(Path(self.tmp.name) / 'hermes.exe', Path(self.tmp.name) / 'hermes', RoomPolicy(False))

        def fake_run(argv, **kwargs):
            self.assertIn('--ignore-rules', argv)
            self.assertNotIn('--resume', argv)
            self.assertEqual(argv[argv.index('--profile') + 1], 'default')
            self.assertEqual(argv[argv.index('--toolsets') + 1], 'clarify')
            kwargs['stdout'].write(json.dumps({'type': 'result', 'exit_code': 0, 'text': 'answer', 'session_id': 'fixture'}))
            return subprocess.CompletedProcess(argv, 0)

        with patch.object(adapter, 'status', return_value={'state': 'ready'}), patch('agent_bridge.chat.hermes.subprocess.run', side_effect=fake_run):
            result = adapter.start_selected('chosen context', 'synthetic')
        self.assertTrue(result['ok'])
