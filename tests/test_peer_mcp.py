import io
import json
import unittest
import os
import subprocess
import sys
from pathlib import Path
from test_peer_rounds import RoundTests
from agent_bridge.peer_mcp import PeerServer


class LocalClient:
    def __init__(self, rounds, caller): self.rounds, self.caller = rounds, caller
    def prepare(self, args): return self.rounds.prepare(self.caller, args)
    def read(self, args): return self.rounds.read(self.caller, args['round_id'])
    def status(self, args): return {'ok': True}


class MCPTests(RoundTests):
    def test_four_callers_use_same_transport_and_only_safe_tools(self):
        for caller in ('codex', 'claude', 'hermes', 'grok'):
            server = PeerServer(caller, LocalClient(self.rounds, caller))
            response = server.handle({'id': 1, 'method': 'initialize'})
            self.assertIn('human', response['result']['instructions'])
            tools = server.handle({'id': 2, 'method': 'tools/list'})['result']['tools']
            self.assertEqual({t['name'] for t in tools}, {'peers_prepare', 'peers_read', 'peers_status'})
            prep = next(t for t in tools if t['name'] == 'peers_prepare')
            self.assertNotIn(caller, prep['inputSchema']['properties']['targets']['items']['enum'])
            self.assertTrue(server.call_tool({'name': 'approve', 'arguments': {}})['isError'])
    def test_reply_returns_to_initiating_mcp_and_cannot_send_again(self):
        server = PeerServer('codex', LocalClient(self.rounds, 'codex'))
        result = server.call_tool({'name': 'peers_prepare', 'arguments': self.args})
        self.assertFalse(result['isError'])
        rid = result['structuredContent']['round_id']
        self.rounds.approve(rid)
        self.rounds.run_once()
        result = server.call_tool({'name': 'peers_read', 'arguments': {'round_id': rid}})
        self.assertIn('ask all other agents!', result['structuredContent']['replies']['claude']['text'])
        self.assertFalse(self.rounds.run_once())
        for args in [[], {'round_id': rid, 'approve': True}]:
            self.assertTrue(server.call_tool({'name': 'peers_read', 'arguments': args})['isError'])
    def test_transport_still_handles_invalid_frames(self):
        server = PeerServer('hermes', LocalClient(self.rounds, 'hermes'))
        out = io.StringIO()
        server.serve(io.StringIO('not json\n'+json.dumps({'id': 2, 'method': 'ping'})+'\n'), out)
        messages = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(messages[0]['error']['code'], -32700)
        self.assertEqual(messages[1]['id'], 2)

    def test_stdio_reply_is_utf8_even_on_legacy_windows_encoding(self):
        code = "from agent_bridge import peer_mcp as m; m.RoomClient.status=lambda self,args: {'ok':True,'text':'\\u03bb\\U0001f331'}; m.main(['--caller','codex','status'])"
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'), PYTHONIOENCODING='cp1252')
        request = json.dumps({'id': 1, 'method': 'tools/call', 'params': {'name': 'peers_status'}})+'\n'
        result = subprocess.run([sys.executable, '-c', code], input=request.encode(), capture_output=True, env=env, shell=False, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.decode('utf-8'))['text'], '\u03bb\U0001f331')


if __name__ == '__main__': unittest.main()
