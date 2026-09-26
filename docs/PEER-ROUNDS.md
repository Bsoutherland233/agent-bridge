# Explicit peer rounds

The local Agent Room provides a bounded, human-approved way for Claude and
Codex to exchange selected context. A round is one request from the human,
one turn from each selected peer, and a final summary from the lead.

The MCP tools only prepare and read rounds. They cannot approve a round, send
messages, or start another round. Approval happens once in the local room UI.
Peer replies are untrusted data and never authorize tools, follow-up calls, or
access to other conversation history.

## Context and privacy

The human selects the question and optional excerpt. The room does not forward
whole histories by default. Only public, synthetic, and internal non-client
classification labels are accepted. Client-derived material, credentials, and
secrets are refused before storage or dispatch.

Room state is stored locally in an owner-only directory. The HTTP server binds
to loopback, requires its bearer token, validates Host and Origin, disables
proxy and redirect handling, and applies request, response, size, and time
limits.

## Setup

Run the local room from the repository:

    python start_chat.py --open

The provider-neutral MCP launcher accepts caller claude or codex:

    python -m agent_bridge.peer_mcp --caller codex

If the room uses a custom state directory, pass the same directory with
--state-dir. Do not expose the stdio service publicly.

## Existing consultation bridge

Peer rounds are an Agent Room feature layered beside the existing codex-peer
consultation tools. The existing bridge remains the direct Claude/Codex
consultation path; peer rounds add a local shared transcript and an explicit
human approval boundary. They do not replace the existing bridge.

## Tests

Offline tests use fake adapters only:

    PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest
      test_chat_discussion test_chat_dispatch test_chat_http
      test_chat_launch test_chat_management test_chat_pending
      test_chat_policy test_chat_storage test_peer_http
      test_peer_mcp test_peer_rounds

No live provider tests are run by this contribution.
