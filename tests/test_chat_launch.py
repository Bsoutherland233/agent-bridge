import sys
import subprocess
from pathlib import Path
from test_chat_storage import StorageTests
from agent_bridge.chat.__main__ import _local_opener, build_app
from unittest.mock import patch


class LaunchTests(StorageTests):
    def test_launcher_sets_private_file_creation_policy_before_database(self):
        from agent_bridge.chat import __main__ as launch
        with patch.object(launch.bridge_store, 'set_umask', wraps=launch.bridge_store.set_umask) as private:
            app = build_app(Path(self.temp.name)/'private-state')
            self.addCleanup(app[0].server_close)
            private.assert_called_once()

    def test_only_provider_neutral_adapters_are_registered(self):
        app = build_app(Path(self.temp.name)/'configured')
        self.addCleanup(app[0].server_close)
        self.assertEqual(set(app[2].adapters), {'claude', 'codex'})

    def test_local_first_large_prompt_is_capped_before_provider_dispatch(self):
        app = build_app(Path(self.temp.name)/'local-first')
        self.addCleanup(app[0].server_close)
        adapter = app[2].adapters['claude']
        adapter.cfg.raw['local_first'] = {'enabled': True, 'read_gate_min_bytes': 1}
        with patch.object(adapter, 'status', return_value={'state': 'ready'}), patch('agent_bridge.chat.adapters.broker.start') as start:
            with self.assertRaises(ValueError):
                adapter.start('large enough', 'synthetic')
        start.assert_not_called()
    def test_existing_instance_probe_disables_proxy_and_redirects(self):
        with patch('agent_bridge.chat.__main__.urllib.request.build_opener') as build:
            _local_opener()
            handlers = build.call_args.args
            self.assertEqual(handlers[0].proxies, {})
            self.assertIsNone(handlers[1].redirect_request(None, None, 302, '', {}, 'http://proxy.invalid'))

    def test_launch_recovers_without_model_calls(self):
        root = Path(self.temp.name) / 'state with spaces'
        app = build_app(root, allow_client=False)
        self.addCleanup(app[0].server_close)
        store = app[1]
        room = store.rooms()[0]['id']
        store.submit(room, 'r', 'test', ['claude'], 'synthetic')
        app[0].server_close()
        restarted = build_app(root, allow_client=False)
        self.addCleanup(restarted[0].server_close)
        self.assertEqual(restarted[1].snapshot(room)['jobs'][0]['status'], 'failed')
        # The runtime stores the canonical filesystem path. On macOS, a
        # temporary directory can be spelled /var/... while resolve() returns
        # /private/var/..., even though both names identify the same folder.
        self.assertEqual(restarted[1].path.parent, root.resolve())

    def test_entrypoint_help_works_from_other_directory(self):
        script = Path(__file__).resolve().parents[1] / 'start_chat.py'
        result = subprocess.run([sys.executable, str(script), '--help'], cwd=self.temp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--open', result.stdout)
