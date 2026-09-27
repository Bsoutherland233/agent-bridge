from pathlib import Path
import os
import json
from unittest.mock import patch

from test_chat_storage import StorageTests
from agent_bridge.chat.grok import GrokAdapter, receive, respond
from agent_bridge.chat.policy import RoomPolicy


class GrokTests(StorageTests):
    def adapter(self, name='grok'):
        root = Path(self.temp.name) / name
        adapter = GrokAdapter(root, RoomPolicy(False))
        (root / 'bot-manifest.json').write_text(json.dumps({
            'product': 'Grok Bot', 'version': 'fixture',
            'tools': ['grok_room.py next --wait', 'grok_room.py reply <job-id>'],
            'allowlist': ['grok_room.py next --wait', 'grok_room.py reply <job-id>'],
            'approved_by': 'Scott'}), encoding='utf-8')
        return adapter

    def test_restart_cancels_unpulled_request(self):
        adapter = self.adapter()
        root = adapter.root
        receive(root, wait=0)
        job = adapter.start('Do not replay after restart', 'synthetic')
        self.adapter()
        self.assertIsNone(receive(root, wait=0))
        self.assertEqual(adapter.poll(job['job_id'])['status'], 'cancelled')

    def test_disconnected_until_local_bot_checks_in(self):
        adapter = self.adapter()
        self.assertNotEqual(adapter.status()['state'], 'ready')
        receive(adapter.root, wait=0)
        self.assertEqual(adapter.status()['state'], 'ready')

    def test_queue_roundtrip_and_only_one_reply(self):
        adapter = self.adapter()
        receive(adapter.root, wait=0)
        job = adapter.start('A synthetic room prompt', 'synthetic')
        pulled = receive(adapter.root, wait=0)
        self.assertTrue(pulled['prompt'].endswith('A synthetic room prompt'))
        self.assertIsNone(receive(adapter.root, wait=0))
        respond(adapter.root, job['job_id'], 'Reply from existing Grok Bot')
        self.assertEqual(adapter.poll(job['job_id'])['status'], 'complete')
        self.assertEqual(adapter.read(job['job_id'])['peer_response'], 'Reply from existing Grok Bot')
        with self.assertRaises(ValueError):
            respond(adapter.root, job['job_id'], 'duplicate')

    def test_expired_and_traversal_jobs_are_refused(self):
        adapter = self.adapter()
        with self.assertRaises(ValueError):
            respond(adapter.root, '../escape', 'bad')
        with self.assertRaises(ValueError):
            respond(adapter.root, '00000000-0000-0000-0000-000000000000', 'unknown')

    def test_unicode_transcript_roundtrip(self):
        adapter = self.adapter()
        receive(adapter.root, wait=0)
        prompt = 'Garden club “Budding” — 🌱'
        job = adapter.start(prompt, 'synthetic')
        self.assertTrue(receive(adapter.root, wait=0)['prompt'].endswith(prompt))
        respond(adapter.root, job['job_id'], prompt)
        self.assertEqual(adapter.read(job['job_id'])['peer_response'], prompt)

    def test_fresh_consultation_marks_new_context(self):
        adapter = self.adapter('fresh')
        receive(adapter.root, wait=0)
        first = adapter.start('Room history', 'synthetic')
        record = receive(adapter.root, wait=0)
        self.assertIn('Fresh room consultation', record['prompt'])
        self.assertTrue(record['prompt'].endswith('Room history'))
        second = adapter.start('Room history', 'synthetic')
        self.assertNotEqual(first['conversation_id'], second['conversation_id'])

    def test_classification_refusal_does_not_create_a_queue_job(self):
        adapter = self.adapter()
        with self.assertRaises(ValueError):
            adapter.start('client text', 'client-derived')
        self.assertEqual(list(adapter.root.glob('*.json')), [adapter.root / 'bot-manifest.json'])

    def test_malformed_foreign_json_is_quarantined(self):
        root = Path(self.temp.name) / 'malformed'
        root.mkdir()
        (root / 'foreign.json').write_text('{"not":"a queue job"}', encoding='utf-8')
        adapter = self.adapter('malformed')
        self.assertTrue((root / 'quarantine').is_dir())
        self.assertIsNone(receive(adapter.root, wait=0))
