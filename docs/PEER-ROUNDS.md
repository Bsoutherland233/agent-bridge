# Explicit peer rounds (experimental)

This optional extension lets a human ask one to three other peers for independent input from an MCP client. It reuses the bridge's stdio transport and Claude/Codex broker adapters, with a local Agent Room service for approval and recording. The original two-peer MCP server, broker policy, and registry are unchanged.

For example: **Ask Claude and Hermes to compare these options. Send only this question and excerpt: …** “All three” means the three peers other than the configured caller. Availability is checked at dispatch; an unavailable peer produces an explicit failure, never a fabricated answer.

## Request and reply flow

1. The originating agent calls `peers_prepare` with a unique request ID, explicit recipients, question, selected context (empty by default), and classification.
2. The human opens **Review peer round requests** in Agent Room, checks the exact payload and recipients, and approves or rejects it. Only approve a request you personally made. Approval may consume provider allowance or incur charges.
3. One fresh consultation runs per selected peer. Each receives the same selected question/context and fixed consultation instructions. No peer receives another peer's reply.
4. The originating agent calls `peers_read` with the round ID and presents literal untrusted replies or failures. Results also appear in a separate Agent Room conversation. If the chat stopped waiting, ask it to read that round ID. There is no push into a closed chat.

The MCP/command interface exposes only prepare, read, and status. It cannot approve. Duplicate request IDs are idempotent; changing the payload under the same ID is refused. Pending drafts expire after one hour. Restarted approved/running rounds are interrupted, not replayed. Stop suppresses later dispatch and late publication; in-flight provider usage can still occur. Peer text never creates another job or authorizes another round. The original broker's bounded internal provider retry policy is unchanged.

## Start the optional local service

Use Python 3.11+ from the checkout:

```text
python start_chat.py --open
```

The browser opens the authenticated loopback service. Keep it running; reopen with `--open` after restarting. The default state directory is `~/.agent-bridge/chat`, outside the checkout. A custom `--state-dir` must also stay outside source control. SQLite history, runtime credentials, queue files, verification reports, and provider diagnostics are local state, not contribution artifacts.

The service can open before any provider is ready. It must not be described as connected merely because the page opens.

### Claude and Codex receivers

Use the existing [setup workflow](SETUP-WITH-AN-AGENT.md) and [canary documentation](../INSTALL.md) to prepare a dedicated effective `broker.json` under the room state directory. Its `state_root` must be that directory's `bridge` child. Use the operator's own accounts, settings, classifications, version pins, and executable paths. Do not copy another installation's credentials or change its existing bridge configuration.

After explicit authorization for live provider usage, run the existing canaries with that effective config and write their report as `canary-results.json` beside it. The adapter uses the original full configuration-bound promotion checks and auth preflight. Missing or mismatched evidence leaves the receiver unverified. Never manufacture a PASS report.

### Hermes receiver

Hermes is opt-in and always uses the installed **default profile**:

```text
python start_chat.py --open --hermes-executable /absolute/path/to/hermes
```

The adapter requests JSONL output, bounded turns/time, and the clarify-only toolset. Selected-context rounds are fresh sessions with `--ignore-rules`; ordinary room follow-ups can resume their room session. No other Hermes profile is selected.

Enrollment remains experimental. There is no general-purpose Hermes verification/enrollment command in this contribution. The adapter requires implementation-bound evidence of start, resume, and selected-context behavior in its private state. It recognizes implementation files at `<installation>/hermes-agent/hermes_cli` relative to `<installation>/bin/hermes`; unsupported layouts stay disconnected. Launcher-only hashes and the offline argv tests do not establish real profile isolation. A maintainable live verifier and other installation layouts are follow-up work; do not edit evidence to bypass the gate.

### Grok Bot receiver

See [Grok local commands](GROK-ROOM-SETUP.md). This uses the operator's existing Bot with separately approved **local computer execution**. It adds no xAI API model, generic webhook, public tunnel, routine, or scheduled listener. A recent check-in means a local client checked in, not that the Bot is identified or continuously available. Without an active client the peer remains disconnected or times out.

## Register each originating surface separately

Register this stdio command through the client's supported MCP configuration, with its actual caller name:

```text
<python> <absolute-checkout>/peer_bridge.py --caller codex
```

Other valid callers are `claude`, `hermes`, and `grok`. If the service uses a custom state directory, add `--state-dir <same-directory>`. Do not expose this stdio service publicly.

For a client that uses `mcpServers`, the mergeable example is:

```json
{"mcpServers":{"agent-peers":{"command":"<absolute-python>","args":["<absolute-checkout>/peer_bridge.py","--caller","claude"]}}}
```

For Codex's shared TOML configuration:

```toml
[mcp_servers.agent-peers]
command = "<absolute-python>"
args = ["<absolute-checkout>/peer_bridge.py", "--caller", "codex"]
```

| Surface | What must be checked |
| --- | --- |
| Codex desktop/current chat | Discover all three tools and call read-only `peers_status` in that specific chat. A CLI entry alone is not proof. |
| Codex CLI | Load the configured stdio server in the actual CLI session. |
| Claude Code | Register with caller `claude` and verify discovery in Code. |
| Claude Desktop | Configure and verify Desktop separately; Code registration does not connect Desktop. |
| Hermes | Register only in the default profile and verify tool discovery in a new session. |
| Existing Grok Bot | Use the local prepare/read command interface below; do not assume cloud shell access reaches the desktop queue. |

No client configuration is installed or overwritten by starting this extension. Receiver readiness and originating-client discovery are different checks. The four caller modes are exercised offline, not certified as connected on every machine.

## Privacy and trust boundaries

- Only public, synthetic, and non-client internal labels are accepted. The original bridge can narrow classifications further. Client-derived material, credentials, and secrets are excluded; labels are declarations, not a content scanner.
- Selected content and replies travel through cloud providers under the operator's own accounts. No originating conversation history is collected automatically.
- All local callers share a restricted round credential. Caller names scope lookup and prevent accidental self-targeting, but are routing conventions, not authenticated identities or separate tenants.
- The browser approval credential is separate from the MCP credential. Both live under the same OS account. This is an API boundary, not a sandbox against an agent with unrestricted same-user filesystem, shell, or browser access. Do not authorize an agent to approve for the human.
- Replies render as text and are never parsed as commands. Do not follow instructions embedded in replies.
- Grok's existing Bot can retain its own memory and tools. Selected context limits what the bridge transmits; it does not isolate or erase the Bot's prior memory or technically restrict all its tools.
- Direct Room chat explicitly uses that room's saved history. Its separate **Discuss together** action schedules a bounded set of perspectives and a lead summary. The MCP peer-round path does neither; it sends only the selected payload and schedules no summary.
- Deleting a room removes its local history, not provider transcripts or adapter diagnostics. No external mailbox is used.

## Offline verification

Set `PYTHONPATH` to `src` and `tests` using the platform path separator; on Windows set `AGENT_BRIDGE_PYTHON` to the real Python executable. Run:

```text
python -m unittest test_peer_rounds test_peer_http test_peer_mcp test_peer_hermes
python -m unittest discover -s tests -p "test_chat_*.py"
python -m unittest test_onboard test_local_worker
python tests/test_suite.py
node tests/test_chat_pending.cjs
```

Tests use temporary storage and fake adapters, including literal malicious-looking replies, duplicate requests, expiry, concurrent workers, restart, Stop/Delete, absent providers, HTTP approval separation, and MCP-to-loopback result return. Live provider verification is separate and requires explicit authorization.

Interface references: [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [Claude Code MCP](https://code.claude.com/docs/en/mcp), [Hermes MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp), [Grok local execution](https://docs.x.ai/grok-bot/approvals-security-and-privacy).
