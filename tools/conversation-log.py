#!/usr/bin/env python3
"""Automatic conversation logging for this project.

Reads Muse's native session logs (JSONL, read-only) and appends the
user-visible conversation -- user prompts and assistant responses -- to
per-session Markdown files in <project>/conversation-log/.

Usage:
    conversation-log.py once    Single pass: backfill/discover sessions (default)
    conversation-log.py watch   Loop forever, tailing logs every --interval seconds

The watcher auto-discovers future sessions for this project by matching the
workspace_root recorded in each session log. State (per-session sequence
checkpoints) lives in conversation-log/.conversation-log-state.json, so
restarts never duplicate entries.

Session names (the human-readable names shown by /resume) are read from
Muse's SQLite session index and recorded next to each session UUID in the
Markdown header. Renames are detected by polling and appended as
chronological notes; previous names are never deleted. When the index is
unavailable, logging falls back to UUID-only.

Safety: this script only READS session logs and the session index. It never
modifies, moves, or deletes them. It uses no network, no subprocesses, and
no Muse API calls, so it cannot interfere with Muse or add token/API costs.

Schema note: validated against Muse Code 1.4.14 session logs and its
session-index database. Both shapes are undocumented and may change in
future releases; unknown shapes are skipped with a stderr warning, never
crash the run.
"""

import argparse
import glob
import json
import os
import sqlite3
import sys
import time
from datetime import datetime

STATE_VERSION = 1
_INDEX_WARNED = False


def default_sessions_root():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(base, "muse", "sessions")


def default_project_root():
    # Script lives at <project>/tools/conversation-log.py
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_index_db():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(base, "muse", "session-index.db")


def read_session_names(index_db, session_ids):
    """Return {session_id: (name, revision)} from Muse's session index.

    Reads the SQLite index read-only. Prefers the canonical session_name
    column with fallback to logged_session_name (the populated one in
    1.4.14). Returns {} on any failure -- missing/locked database or an
    unexpected schema -- so callers degrade to UUID-only logging. Warns
    once per process; never raises.
    """
    global _INDEX_WARNED
    if not session_ids:
        return {}
    try:
        con = sqlite3.connect(f"file:{index_db}?mode=ro", uri=True, timeout=5)
        try:
            rows = con.execute(
                "SELECT session_id, "
                "COALESCE(session_name, logged_session_name), "
                "COALESCE(session_name_revision, logged_session_name_revision) "
                f"FROM sessions WHERE session_id IN "
                f"({','.join('?' for _ in session_ids)})",
                list(session_ids),
            ).fetchall()
        finally:
            con.close()
    except (sqlite3.Error, OSError) as exc:
        if not _INDEX_WARNED:
            print(
                f"warning: session index unavailable ({exc}); logging UUID-only",
                file=sys.stderr,
            )
            _INDEX_WARNED = True
        return {}
    _INDEX_WARNED = False
    return {sid: (name, rev) for sid, name, rev in rows if name}


def iter_inner_records(line):
    """Yield parsed records from one JSONL line, unwrapping framed children.

    Most lines are records themselves. Some lines are retained_frame envelopes
    whose children carry their record as an embedded JSON string (record_json).
    Raises ValueError on malformed JSON (caller treats as a torn write and
    retries the line on the next pass).
    """
    top = json.loads(line)
    if isinstance(top, dict) and "payload_type" in top:
        yield top
        return
    for child in top.get("children", []) if isinstance(top, dict) else []:
        if isinstance(child, dict) and isinstance(child.get("record_json"), str):
            yield json.loads(child["record_json"])


def find_workspace_root(path, max_records=500):
    """Return the workspace_root recorded in a session log, or None.

    The marker lives in a runtime.session.metadata record near the start of
    the log. Returns None when absent (e.g. a brand-new session whose startup
    records are not yet flushed) -- callers must re-check later.
    """
    checked = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records = list(iter_inner_records(line))
                except ValueError:
                    continue  # torn write; stop scanning, not fatal
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    payload = rec.get("payload")
                    if not isinstance(payload, dict):
                        continue
                    record = payload.get("record")
                    if isinstance(record, dict) and record.get("workspace_root"):
                        return record["workspace_root"]
                    checked += 1
                    if checked >= max_records:
                        return None
    except (OSError, UnicodeDecodeError):
        return None
    return None


def discover_sessions(sessions_root, project_root, state):
    """Return {session_id: info} for project sessions, updating cached state.

    Sessions whose workspace does not match are cached in state["ignored"] so
    they are never scanned again. Sessions with no workspace marker yet are
    re-checked on every pass (they may be newly started sessions).
    """
    project_root = os.path.realpath(project_root)
    ignored = state.setdefault("ignored", {})
    found = {}
    pattern = os.path.join(sessions_root, "*", "*", "*", "*", "session.jsonl")
    for path in glob.glob(pattern):
        session_id = os.path.basename(os.path.dirname(path))
        if session_id in ignored:
            continue
        cached = state.get("sessions", {}).get(session_id)
        if cached is not None:
            found[session_id] = {"path": path, "workspace_root": cached["workspace_root"]}
            continue
        root = find_workspace_root(path)
        if root is None:
            continue  # undecided; re-check next pass
        if os.path.realpath(root) == project_root:
            # Date shards: .../YYYY/MM/DD/<session-id>/session.jsonl
            parts = path.split(os.sep)
            date = "-".join(parts[-5:-2]) if len(parts) >= 5 else "unknown-date"
            found[session_id] = {"path": path, "workspace_root": root, "date": date}
        else:
            ignored[session_id] = root
    return found


def extract_entries(path, after_sequence):
    """Yield (sequence, speaker, text, recorded_at) for new conversation records.

    Only user-visible conversation is extracted:
      user:      run "started" prompt (non-empty), else the run's
                 "user_prompt_display" text (even a placeholder like "[Image 1]",
                 which at least records that a user turn occurred), plus
                 "user_steer" inbox items queued mid-run.
      assistant: "assistant_message_committed" text.
    Tool calls/results, encrypted reasoning blobs, background inbox items, and
    empty internal child-run prompts are intentionally excluded.

    Returns (entries, max_sequence). Sequence numbers are the dedup
    checkpoint: callers persist the max and pass it back as after_sequence.
    On a malformed trailing line (torn write while Muse is appending),
    scanning stops before that line; already-yielded entries still carry
    their sequences, so nothing is lost or duplicated.
    """
    entries = []
    run_has_prompt = {}  # run_id -> bool (non-empty started prompt seen)
    pending_runs = set()  # run_ids with started record seen
    max_seq = after_sequence
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    records = list(iter_inner_records(line.strip()))
                except ValueError:
                    break  # torn trailing write; retry it next pass
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    seq = rec.get("sequence")
                    if not isinstance(seq, int):
                        continue
                    if seq > max_seq:
                        max_seq = seq
                    if seq <= after_sequence:
                        continue
                    payload = rec.get("payload")
                    if not isinstance(payload, dict):
                        continue
                    event = payload.get("event")
                    if not isinstance(event, dict):
                        continue
                    kind = event.get("kind")
                    run_id = payload.get("run_id")
                    ts = rec.get("recorded_at")
                    if kind == "started" and payload.get("kind") == "run":
                        pending_runs.add(run_id)
                        prompt = event.get("prompt")
                        if isinstance(prompt, str) and prompt:
                            run_has_prompt[run_id] = True
                            entries.append((seq, "user", prompt, ts))
                        # Empty prompt = internal child run, not user speech:
                        # skipped (counted by caller via skipped_empty).
                    elif kind == "user_prompt_display":
                        if run_id not in pending_runs or not run_has_prompt.get(run_id):
                            text = event.get("prompt")
                            if isinstance(text, str) and text:
                                run_has_prompt[run_id] = True
                                entries.append((seq, "user", text, ts))
                        # Else: full text already captured from started.prompt.
                    elif kind == "inbox_item_queued":
                        source = event.get("source")
                        origin = source.get("source") if isinstance(source, dict) else None
                        if origin == "user_steer":
                            text = None
                            inner = event.get("payload")
                            if isinstance(inner, dict) and isinstance(
                                inner.get("prompt"), str
                            ):
                                text = inner["prompt"]
                            elif isinstance(event.get("body"), str):
                                text = event["body"]
                            if text:
                                entries.append((seq, "user", text, ts))
                        # Other origins (background/scheduled deliveries) are
                        # not user speech and are excluded.
                    elif kind == "assistant_message_committed":
                        text = event.get("text")
                        if isinstance(text, str) and text:
                            entries.append((seq, "assistant", text, ts))
    except (OSError, UnicodeDecodeError) as exc:
        print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
        return entries, after_sequence
    entries.sort(key=lambda e: e[0])
    return entries, max_seq


def format_timestamp(recorded_at):
    if isinstance(recorded_at, (int, float)):
        try:
            return datetime.fromtimestamp(recorded_at / 1e6).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            pass
    return "unknown time"


def format_entry(speaker, text, recorded_at):
    label = "You" if speaker == "user" else "Muse"
    body = text if text.endswith("\n") else text + "\n"
    return f"---\n## {label} \u00b7 {format_timestamp(recorded_at)}\n\n{body}\n"


def load_state(state_path):
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        if isinstance(state, dict) and state.get("version") == STATE_VERSION:
            state.setdefault("sessions", {})
            state.setdefault("ignored", {})
            return state
    except (OSError, ValueError):
        pass
    return {"version": STATE_VERSION, "sessions": {}, "ignored": {}}


def save_state(state_path, state):
    tmp = state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, state_path)


def ensure_header_name(log_path, name):
    """Sync the '- Session name:' header line. Returns True if changed."""
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    marker = "- Session name:"
    for i, line in enumerate(lines):
        if line.startswith(marker):
            if line.rstrip("\n") == f"{marker} {name}":
                return False
            lines[i] = f"{marker} {name}\n"
            break
    else:
        for i, line in enumerate(lines):
            if line.startswith("- Session ID:"):
                lines.insert(i + 1, f"{marker} {name}\n")
                break
        else:
            return False  # unexpected header shape; leave untouched
    with open(log_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return True


def format_rename_note(old, new, stamp):
    return f"---\n*Session renamed: `{old}` \u2192 `{new}` \u00b7 {stamp}*\n\n"


def process_session(session_id, info, log_dir, entry, name_info):
    """Append new entries for one session.

    name_info is a (name, revision) tuple from the session index, or None.
    Returns (conversation_count, rename_note_or_None).
    """
    name, revision = name_info if name_info else (None, None)
    path = info["path"]
    last_seq = entry.get("last_sequence", 0)
    entries, max_seq = extract_entries(path, last_seq)
    entry["last_sequence"] = max_seq
    date = entry.get("date") or info.get("date") or "unknown-date"
    log_name = f"{date}_{session_id}.md"
    log_path = os.path.join(log_dir, log_name)
    if not os.path.exists(log_path):
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(
                f"# Conversation \u2014 {date} (session {session_id[:8]}\u2026)\n"
                f"\n- Session ID: {session_id}\n"
            )
            if name:
                f.write(f"- Session name: {name}\n")
            f.write(
                f"- Date: {date}\n"
                f"- Workspace: {entry.get('workspace_root', '')}\n"
                "- Source: Muse native session log (automatic; do not edit below this line)\n"
                "\n"
            )
    rename_note = None
    if name:
        prev_name = entry.get("current_name")
        if prev_name is None:
            # First sighting: adopt the name, sync the header, no note.
            entry["current_name"] = name
            entry["current_revision"] = revision
            ensure_header_name(log_path, name)
        elif name != prev_name:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rename_note = format_rename_note(prev_name, name, stamp)
            entry.setdefault("name_history", []).append(
                {"from": prev_name, "to": name, "at": stamp}
            )
            entry["current_name"] = name
            entry["current_revision"] = revision
            ensure_header_name(log_path, name)
        elif revision != entry.get("current_revision"):
            entry["current_revision"] = revision  # silent revision-only bump
    if entries or rename_note:
        with open(log_path, "a", encoding="utf-8") as f:
            for seq, speaker, text, ts in entries:
                f.write(format_entry(speaker, text, ts))
                f.flush()
                os.fsync(f.fileno())
            if rename_note:
                f.write(rename_note)
                f.flush()
                os.fsync(f.fileno())
    entry["log_file"] = log_name
    return len(entries), rename_note


def run_once(sessions_root, project_root, log_dir, state_path, index_db, verbose=False):
    os.makedirs(log_dir, exist_ok=True)
    state = load_state(state_path)
    sessions = discover_sessions(sessions_root, project_root, state)
    names = read_session_names(index_db, list(sessions))
    total = 0
    for session_id in sorted(sessions):
        entry = state["sessions"].setdefault(
            session_id,
            {
                "workspace_root": sessions[session_id]["workspace_root"],
                "date": sessions[session_id].get("date", "unknown-date"),
                "last_sequence": 0,
            },
        )
        try:
            count, rename_note = process_session(
                session_id, sessions[session_id], log_dir, entry, names.get(session_id)
            )
        except (OSError, UnicodeDecodeError) as exc:
            print(f"warning: session {session_id[:8]}: {exc}", file=sys.stderr)
            continue
        total += count
        if verbose and (count or rename_note):
            msg = f"session {session_id[:8]}: +{count} entries -> {entry.get('log_file')}"
            if rename_note:
                msg += f" [renamed to {entry.get('current_name')}]"
            print(msg)
        save_state(state_path, state)  # checkpoint after every session
    save_state(state_path, state)
    return total, len(sessions)


def run_watch(sessions_root, project_root, log_dir, state_path, index_db, interval):
    print(
        f"watching {sessions_root} for project sessions "
        f"(interval {interval}s, logs in {log_dir})",
        flush=True,
    )
    known = set()
    while True:
        total, _ = run_once(sessions_root, project_root, log_dir, state_path, index_db)
        state = load_state(state_path)
        current = set(state.get("sessions", {}))
        for sid in sorted(current - known):
            print(f"new project session discovered: {sid}", flush=True)
        known = current
        if total:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"{stamp}: appended {total} entries", flush=True)
        time.sleep(interval)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Log project Muse conversations to Markdown.")
    parser.add_argument("mode", nargs="?", default="once", choices=["once", "watch"])
    parser.add_argument("--project-root", default=default_project_root())
    parser.add_argument(
        "--sessions-root",
        default=os.environ.get("MUSE_SESSIONS_ROOT") or default_sessions_root(),
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--state-file", default=None)
    parser.add_argument("--index-db", default=None)
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    log_dir = args.log_dir or os.path.join(args.project_root, "conversation-log")
    state_path = args.state_file or os.path.join(log_dir, ".conversation-log-state.json")
    index_db = args.index_db or default_index_db()

    if args.mode == "watch":
        run_watch(
            args.sessions_root, args.project_root, log_dir, state_path, index_db, args.interval
        )
    else:
        total, n_sessions = run_once(
            args.sessions_root, args.project_root, log_dir, state_path, index_db, args.verbose
        )
        print(f"sessions: {n_sessions}, entries appended: {total}")


if __name__ == "__main__":
    main()
