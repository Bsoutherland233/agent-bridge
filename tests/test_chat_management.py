from test_chat_storage import StorageTests

class RoomManagementTests(StorageTests):
    def test_rename_preserves_history(self):
        self.store.submit(self.room,'r','keep this',[],'public')
        self.store.rename_room(self.room,'  New name  ')
        self.assertEqual(self.store.rooms()[0]['title'],'New name')
        self.assertEqual(self.store.snapshot(self.room)['messages'][0]['text'],'keep this')
        for name in ('',' '*3,'x'*101):
            with self.assertRaises(ValueError): self.store.rename_room(self.room,name)
    def test_delete_removes_room_data_and_discards_inflight_reply(self):
        other=self.store.create_room('Keep')['id']
        self.store.preferences(self.room,'codex',['claude','codex'])
        self.store.submit(self.room,'r','topic',['claude','codex'],'public',mode='discuss',lead='codex')
        job=self.store.claim_next()
        self.store.delete_room(self.room)
        self.store.finish(job,'late reply','public','session')
        self.assertEqual([r['id'] for r in self.store.rooms()],[other])
        with self.store.db() as db:
            for table in ('messages','requests','jobs','sessions','room_preferences','discussion_jobs'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
        self.assertFalse(self.store.is_running(job['id']))
