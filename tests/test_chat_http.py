import http.client
import json
import threading
from test_chat_storage import StorageTests
from agent_bridge.chat.dispatch import Dispatcher
from agent_bridge.chat.server import create_server


class HTTPTests(StorageTests):
    def setUp(self):
        super().setUp()
        self.server = create_server(self.store, Dispatcher(self.store, {}), 'test-token')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup_server)
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)

    def cleanup_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        h = {'Authorization': 'Bearer test-token', 'Origin': self.origin, 'Content-Type': 'application/json'}
        h.update(headers or {})
        conn.request(method, path, json.dumps(body) if body is not None else None, h)
        response = conn.getresponse()
        result = response.status, response.read()
        conn.close()
        return result

    def test_missing_auth_and_foreign_origin_are_refused(self):
        for headers in [{'Authorization': ''}, {'Origin': 'https://evil.example'}, {'Host': 'evil.example'}]:
            self.assertEqual(self.request('GET', '/api/rooms', headers=headers)[0], 403)

    def test_note_roundtrip_and_literal_content(self):
        body = {'request_id': 'x', 'text': '<script>alert(1)</script>', 'recipients': [], 'classification': 'public', 'mode': 'note'}
        self.assertEqual(self.request('POST', f'/api/rooms/{self.room}/messages', body)[0], 200)
        status, data = self.request('GET', f'/api/rooms/{self.room}')
        self.assertEqual(status, 200)
        snapshot = json.loads(data)
        self.assertEqual(snapshot['messages'][0]['text'], body['text'])
        self.assertEqual(snapshot['jobs'], [])

    def test_bad_paths_and_oversized_body(self):
        self.assertEqual(self.request('GET', '/../../config/broker.json')[0], 404)
        self.assertEqual(self.request('POST', '/api/rooms', {'title': 'x' * 70000})[0], 413)

    def test_unavailable_recipient_is_rejected_before_save(self):
        body = {'request_id': 'x', 'text': 'hello', 'recipients': ['grok'], 'classification': 'public'}
        self.assertEqual(self.request('POST', f'/api/rooms/{self.room}/messages', body)[0], 400)
        self.assertEqual(self.store.snapshot(self.room)['messages'], [])
    def test_rename_and_delete_require_confirmation(self):
        self.assertEqual(self.request('POST',f'/api/rooms/{self.room}/rename',{'title':'Renamed'})[0],200)
        self.assertEqual(self.store.rooms()[0]['title'],'Renamed')
        self.assertEqual(self.request('POST',f'/api/rooms/{self.room}/delete',{})[0],400)
        self.assertEqual(len(self.store.rooms()),1)
        self.assertEqual(self.request('POST',f'/api/rooms/{self.room}/delete',{'confirm':True})[0],200)
        self.assertEqual(self.store.rooms(),[])
