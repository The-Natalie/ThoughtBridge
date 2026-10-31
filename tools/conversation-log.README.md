# Conversation logging (project-specific)

Automatic, local-only logging of your Muse Code conversations for this
project. Nothing here touches the Deterministic Workflow starter.

## What it does

`tools/conversation-log.py` (Python standard library only) reads Muse's
native session logs and appends the user-visible conversation to
per-session Markdown files in `conversation-log/`:

- `## You · <timestamp>` for your prompts, `## Muse · <timestamp>` for replies
- `---` separators between exchanges, full message text, never truncated
- Each log header shows the session UUID plus the human-readable session
  name from `/resume` (e.g. `still-protostar`), read automatically from
  Muse's session index — no manual naming needed
- Renames are detected by polling and appended as timestamped notes
  (`Session renamed: old → new`); previous names are preserved, and the
  header always shows the current name
- Incremental: entries are appended (and flushed) as they appear
- Idempotent: per-session sequence checkpoints in
  `.conversation-log-state.json` mean re-runs and restarts never duplicate
  entries, headers, or rename notes

Future sessions are discovered automatically by matching the
`workspace_root` recorded in each session log. Sessions for other
projects are ignored.

## Usage

```bash
# One pass: backfill everything, then exit (safe to re-run any time)
python3 tools/conversation-log.py once

# Continuous watcher (the LaunchAgent runs this for you)
python3 tools/conversation-log.py watch --interval 15
```

## Automatic startup (macOS LaunchAgent)

```bash
# Install (or reinstall after moving the project): starts now + on every login
bash tools/install-conversation-log-agent.sh

# Check it is running
launchctl print gui/$UID/com.thoughtbridge.conversation-log | head -n 5
tail -n 20 conversation-log/watcher.log

# Stop / remove
launchctl bootout gui/$UID/com.thoughtbridge.conversation-log
rm ~/Library/LaunchAgents/com.thoughtbridge.conversation-log.plist
```

## Safety and privacy

- Session logs are opened read-only; the logger never modifies, moves, or
  deletes them, runs no subprocesses, uses no network, and makes no API
  calls — zero token cost, zero interference with Muse.
- `conversation-log/` is gitignored. Logs contain everything typed, including
  secrets — keep them local. To share a session, use
  `muse export --session <id> --redacted` instead.

## What is (and is not) captured

Captured: full user prompts (including mid-run steered prompts and
image/attachment turns, which appear as their `[placeholder]` label),
and full assistant messages.

Skipped by design: tool calls/results, encrypted reasoning blobs,
background-task deliveries, approval records, and empty internal child-run
prompts (these carry no user speech). Subagent session files under
`subagent/` are not scanned — they contain worker activity, not conversation.

Limitation: the parser was validated against Muse Code 1.4.14 session logs,
whose record shapes are undocumented and may change. Unknown shapes are
skipped with a warning on stderr, never crash the run. The
`user_steer` inbox shape is implemented from product documentation and
covered by synthetic tests; it has not yet been observed in a live session.

Session-name notes: names come from the `sessions` table in
`~/.local/share/muse/session-index.db` (read-only;
`COALESCE(session_name, logged_session_name)`), which is also
undocumented and may change — if the index is missing, locked, or has an
unexpected shape, logging falls back to UUID-only with a stderr warning.
Rename-note timestamps record when the logger detected the change, not
when the rename happened. A live rename has not been observed yet, so
rename handling is covered by synthetic tests only.
