import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agent_bridge.chat.storage import RoomStore


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'room.sqlite'
        self.store = RoomStore(self.path)
        self.room = self.store.create_room('Our agents')['id']

    def test_duplicate_request_has_one_message_and_jobs(self):
        first = self.store.submit(self.room, 'request-1', 'Hello', ['claude', 'codex'], 'public')
        self.assertEqual(first, self.store.submit(self.room, 'request-1', 'Hello', ['claude', 'codex'], 'public'))
        snapshot = RoomStore(self.path).snapshot(self.room)
        self.assertEqual([m['text'] for m in snapshot['messages']], ['Hello'])
        self.assertEqual(len(snapshot['jobs']), 2)
        self.assertEqual(len({j['through_seq'] for j in snapshot['jobs']}), 1)
        with self.assertRaises(ValueError):
            self.store.submit(self.room, 'request-1', 'changed', [], 'public')

    def test_restart_never_replays_work(self):
        self.store.submit(self.room, 'r', 'hello', ['claude'], 'public')
        reopened = RoomStore(self.path)
        self.assertEqual(reopened.recover_interrupted(), 1)
        self.assertEqual(reopened.snapshot(self.room)['jobs'][0]['status'], 'failed')
        self.assertIsNone(reopened.claim_next())

    def test_invalid_submission_writes_nothing(self):
        for text, peers, label in [('', [], 'public'), ('x', ['stranger'], 'public'), ('x', [], 'secret')]:
            with self.assertRaises(ValueError):
                self.store.submit(self.room, 'r', text, peers, label)
        self.assertEqual(self.store.snapshot(self.room)['messages'], [])

    def test_note_without_recipient_is_saved(self):
        self.store.submit(self.room, 'r', 'Just a note', [], 'internal')
        self.assertIsNone(self.store.claim_next())
        self.assertEqual(self.store.snapshot(self.room)['messages'][0]['author'], 'Human')

    def test_explicit_note_mode_is_saved_without_jobs(self):
        result = self.store.submit(self.room, 'note-1', 'Just a note', [], 'internal', mode='note')
        self.assertEqual(result['job_ids'], [])
        self.assertEqual(self.store.submit(self.room, 'note-1', 'Just a note', [], 'internal', mode='note'), result)
        snapshot = self.store.snapshot(self.room)
        self.assertEqual([m['text'] for m in snapshot['messages']], ['Just a note'])
        self.assertEqual(snapshot['jobs'], [])

    def test_new_room_does_not_preselect_optional_hermes(self):
        store = RoomStore(Path(self.temp.name) / 'hermes.sqlite', participants=('claude', 'codex', 'hermes'))
        room = store.create_room('Optional Hermes')['id']
        self.assertEqual(store.preferences(room), {'lead': 'claude', 'participants': ['claude', 'codex']})

if __name__ == '__main__':
    unittest.main()
