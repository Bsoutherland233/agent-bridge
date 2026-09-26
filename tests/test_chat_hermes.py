import json
import subprocess
from pathlib import Path
from unittest.mock import patch
from test_chat_storage import StorageTests
from agent_bridge.chat.hermes import HermesAdapter, decode_result
from agent_bridge.chat.policy import RoomPolicy


class HermesTests(StorageTests):
    def test_launcher_only_fingerprint_cannot_establish_hermes_readiness(self):
        executable = Path(self.temp.name)/'bin'/'hermes.exe'
        executable.parent.mkdir()
        executable.write_bytes(b'fixture launcher')
        adapter = HermesAdapter(executable, Path(self.temp.name)/'evidence', RoomPolicy(False))
        with self.assertRaises(ValueError): adapter.fingerprint()

    def test_selected_context_needs_separate_verification_evidence(self):
        adapter = HermesAdapter(Path(self.temp.name)/'hermes', Path(self.temp.name)/'evidence', RoomPolicy(False))
        evidence = {'fingerprint':'fixture', 'profile':'default', 'start_pass':True, 'resume_pass':True}
        (adapter.root/'verification.json').write_text(json.dumps(evidence), encoding='utf-8')
        with patch.object(adapter, 'fingerprint', return_value='fixture'), patch('agent_bridge.chat.hermes.verify_private_directory'):
            self.assertNotEqual(adapter.status()['state'], 'ready')
            evidence['selected_pass'] = True
            (adapter.root/'verification.json').write_text(json.dumps(evidence), encoding='utf-8')
            self.assertEqual(adapter.status()['state'], 'ready')

    def test_only_terminal_success_with_session_is_accepted(self):
        text, session = decode_result(json.dumps({'type':'result','exit_code':0,'text':'Hello','session_id':'session-123'}), 0)
        self.assertEqual((text, session), ('Hello', 'session-123'))
        for event in [dict(type='result',exit_code=1,text='no',session_id='s'),dict(type='text',text='partial'),dict(type='result',exit_code=0,text='hi',session_id='--bad')]:
            with self.assertRaises(ValueError): decode_result(json.dumps(event), 0)

    def test_default_profile_and_resumed_session_use_room_context(self):
        executable = Path(self.temp.name) / 'hermes.exe'
        executable.write_bytes(b'fake executable for offline test')
        adapter = HermesAdapter(executable, Path(self.temp.name)/'hermes', RoomPolicy(False))
        def run(argv, **kwargs):
            self.assertEqual(argv[1:4], ['--profile', 'default', 'chat'])
            self.assertIn('--resume', argv)
            self.assertEqual(argv[argv.index('--resume')+1], 'session-123')
            self.assertNotIn('--yolo', argv)
            self.assertEqual(argv[argv.index('--toolsets')+1], 'clarify')
            self.assertEqual(kwargs['input'], 'Shared room message')
            kwargs['stdout'].write(json.dumps({'type':'result','exit_code':0,'text':'Real parsed reply','session_id':'session-123'}))
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(adapter, 'status', return_value={'state':'ready'}), patch('agent_bridge.chat.hermes.subprocess.run', side_effect=run):
            result = adapter.continue_('session-123', 'Shared room message', 'synthetic')
        self.assertEqual(adapter.read(result['job_id'])['peer_response'], 'Real parsed reply')
        self.assertEqual(result['conversation_id'], 'session-123')

    def test_missing_evidence_cannot_claim_ready(self):
        adapter = HermesAdapter(Path(self.temp.name)/'absent.exe', Path(self.temp.name)/'hermes', RoomPolicy(False))
        self.assertNotEqual(adapter.status()['state'], 'ready')

    def test_client_prompt_requires_native_profile_storage_verification(self):
        adapter = HermesAdapter(Path(self.temp.name)/'hermes.exe', Path(self.temp.name)/'hermes', RoomPolicy(False))
        with patch.object(adapter,'status',return_value={'state':'ready'}), patch('agent_bridge.chat.hermes.subprocess.run',side_effect=AssertionError('Client prompt reached unverified profile')):
            with self.assertRaises(ValueError):
                adapter.start('client fixture','client-derived')
    def test_unicode_reply_preserved(self):
        from agent_bridge import store
        import uuid
        adapter=HermesAdapter(Path(self.temp.name)/'hermes.exe',Path(self.temp.name)/'unicode',RoomPolicy(False))
        job=str(uuid.uuid4()); folder=adapter.root/job; folder.mkdir()
        store.atomic_write_json(str(folder/'result.json'),{'ok':True,'peer_response':'\u201cHello\u201d \u2014 \U0001f331'})
        self.assertEqual(adapter.read(job)['peer_response'],'\u201cHello\u201d \u2014 \U0001f331')
