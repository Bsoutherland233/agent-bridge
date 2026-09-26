import http.client
import json
import threading
from test_peer_rounds import RoundTests
from agent_bridge.chat.dispatch import Dispatcher
from agent_bridge.chat.server import create_server
from agent_bridge.peer_mcp import RoomClient, PeerServer
from unittest.mock import patch


class PeerHTTPTests(RoundTests):
    def setUp(self):
        super().setUp()
        self.server = create_server(self.store, Dispatcher(self.store, self.adapters), 'human-token', rounds=self.rounds, rounds_token='client-token')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup_server)
    def cleanup_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
    def request(self, method, path, data=None, token='client-token'):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        headers = {'Authorization': 'Bearer '+token, 'Origin': 'http://127.0.0.1:'+str(self.server.server_port), 'Content-Type': 'application/json'}
        conn.request(method, path, None if data is None else json.dumps(data), headers)
        r = conn.getresponse()
        result = (r.status, r.read())
        conn.close()
        return result
    def test_client_cannot_approve_or_access_room_history(self):
        code, payload = self.request('POST', '/api/peer-rounds/codex/prepare', self.args)
        self.assertEqual(code, 200)
        rid = json.loads(payload)['round_id']
        for path in ['/api/rooms', '/api/peer-approvals']:
            self.assertEqual(self.request('GET', path)[0], 403)
        self.assertEqual(self.request('POST', '/api/peer-approvals/'+rid, {'approve': True})[0], 403)
        self.assertFalse(self.rounds.run_once())
        self.assertEqual(self.request('POST', '/api/peer-approvals/'+rid, {'approve': True}, token='human-token')[0], 200)
        self.rounds.run_once()
        code, payload = self.request('GET', '/api/peer-rounds/codex/'+rid)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(payload)['status'], 'completed')
    def test_approval_page_is_static_and_does_not_send(self):
        code, page = self.request('GET', '/peer-rounds')
        self.assertEqual(code, 200)
        self.assertIn(b'Approve', page)
        self.assertEqual(self.request('POST', '/api/peer-rounds/codex/approve', {})[0], 404)

    def test_mcp_through_real_loopback_transport(self):
        root = self.store.path.parent
        (root/'peer-runtime.json').write_text(json.dumps({'port': self.server.server_port, 'token': 'client-token'}))
        server = PeerServer('codex', RoomClient('codex', root))
        # This test isolates ACL policy (covered by existing native ACL tests).
        with patch('agent_bridge.peer_mcp.verify_private_directory'):
            pending = server.call_tool({'name': 'peers_prepare', 'arguments': self.args})
            self.assertFalse(pending['isError'])
            rid = pending['structuredContent']['round_id']
            self.assertFalse(self.rounds.run_once())
            self.request('POST', '/api/peer-approvals/'+rid, {'approve': True}, token='human-token')
            self.rounds.run_once()
            answer = server.call_tool({'name': 'peers_read', 'arguments': {'round_id': rid}})
            self.assertFalse(answer['isError'])
            self.assertEqual(len(answer['structuredContent']['replies']), 1)
            self.assertEqual(answer['structuredContent']['status'], 'completed')

    def test_round_client_rejects_path_traversal_before_http(self):
        client = RoomClient('codex', self.store.path.parent)
        with self.assertRaises(ValueError): client.read({'round_id': '../peer-approvals'})
