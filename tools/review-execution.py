#!/usr/bin/env python3
"""Independent evidence review of a feature plan and execution report.

Pipeline: the plan and report go to an independent reviewer model in ONE
fresh-context API call; the model returns structured JSON (validation
assessments, file operations, findings, manual checks); this script verifies
each reported file operation against the filesystem, computes the overall
status, and renders a short Markdown checklist. No review is written when the
model's output is unusable.

Stdlib only. The script never runs tests, starts servers, installs anything,
or modifies code, the plan, or the report. Run from the repository root.

Usage:
    python3 tools/review-execution.py --plan <plan.md> --report <report.md>

Staged (sandboxed shells): add --reviews-dir <tmpdir> --final-review-path
<canonical review path> so the delegate prompt quotes the permanent path.

Reviews are saved to .agents/execution-reports/reviews/ as
<deliverable-name>-execution-report-review.md (no timestamps; the
deliverable name is the plan file's stem). Reruns automatically replace
the existing review for that deliverable; the execution report is never
modified.

Loop budget (no API call): --loop-state --report <report.md> prints the
follow-up total and this run's remaining corrections; pass --run-start N
with the total observed at invocation start on later queries.

Config (JSON): api_url (OpenAI-compatible chat-completions endpoint), model,
api_key_env (env var naming the API key), max_output_tokens, temperature.
The API key is read from that env var, falling back to a KEY=VALUE entry in
./.env. The key is never printed.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "review-execution.config.json")
DEFAULT_REVIEWS_DIR = os.path.join(".agents", "execution-reports", "reviews")
REQUEST_TIMEOUT_SECONDS = 600

SYSTEM_PROMPT = """You are an independent evidence reviewer — a second set of eyes on a completed AI-assisted feature implementation. You did NOT implement anything and have NO access to the implementation environment. Your only evidence is the feature plan and execution report in the user message. A script verifies file existence separately from your analysis: you identify the file operations, never declare a file present or absent.

Compare the plan against the report, reason carefully, and output a SINGLE JSON object — no Markdown, no commentary, no code fences, no text before or after — with exactly these keys:

{"validations": [{"name": "...", "status": "PASS|FAIL|NOT_VERIFIED", "note": "..."}], "files": [{"op": "created|modified|removed|renamed", "path": "...", "new_path": "...", "change_evidenced": true|false, "uncertain": false, "note": "..."}], "needs_attention": [{"finding": "..."}], "delegate_prompt": "...", "human_checks": [{"check": "...", "where": "...", "steps": ["...", "..."], "expected": "...", "cleanup": "..."}]}

VALIDATIONS
- List every validation the plan required: task-level checks and final validation levels/commands.
- Status rules (no other status exists): PASS means recorded evidence shows the check ran and met the plan's expected result. FAIL means evidence shows it ran and did not meet expectations. NOT_VERIFIED means it was not performed, its result was not recorded, or the evidence is insufficient.
- Ground every entry in what the plan actually required. Never trust completion claims about a plan-required check without supporting recorded output. A check absent from the report was NOT performed — never treat absence as success.
- Do not invent completion criteria the plan never stated, and do not demand specific verification methods (verbatim reruns, scans, greps, clean-shell repetition) unless the plan required them. Omit optional improvement ideas entirely — anything the plan did not require is outside this review.
- A test passing does not automatically prove the requirement: ask whether the assertions actually establish it. Implementation alone is never verification.
- Recognize equivalent procedures: if a check could not run as written but an alternative tested the SAME assertion and reportedly passed, status PASS with a note like "passed via equivalent procedure".
- Consolidate redundant successful checks (e.g. per-task reruns superseded by the final suite) into one entry, but NEVER consolidate away a FAIL, NOT_VERIFIED, or skipped check.
- Cover acceptance criteria: if important behavior was implemented but not adequately tested, add a validation entry (NOT_VERIFIED, or FAIL when evidence shows failure) so it cannot pass silently. Add such entries only for gaps that could hide a genuine failure of the deliverable — never to polish an already convincing record.
- Keep names short ("Unit tests: 68/68", "DB migration", "Frontend rendering"). Put the key expected-vs-recorded detail in note, one sentence.

FILES
- Identify real file operations from BOTH documents: what the plan intended and what the report says happened. Understand ordinary sentences ("Created api/health.py", "Removed old_module.py", "Updated config.py", "Renamed a.py to b.py") as well as file lists.
- op is created, modified, removed, or renamed (renamed requires new_path).
- path and new_path must be PROJECT-RELATIVE paths (e.g. "backend/app/main.py"), resolved using the plan's paths. List files, not directories.
- IGNORE dependency/package names, filenames inside code examples or quoted commands, module specifiers (e.g. "vite/client"), and files merely mentioned in passing. Only real operations on repo files.
- If the plan required a file operation the report never mentions, still include it and say so in note.
- If you cannot determine a confident project-relative path, give your best path and set uncertain: true.
- For modified: change_evidenced is true ONLY if the report contains concrete evidence of the intended change (quoted diff, targeted test output, explicit before/after confirmation). Existence claims or passing unrelated tests do not count. Omit change_evidenced for other ops.
- note: one short sentence max (e.g. "planned + reported", "planned but unmentioned in report").

NEEDS_ATTENTION
- Include ONLY required validations that are NOT_VERIFIED or FAIL, plus genuine contradictions between recorded evidence and completion claims. Each finding is one concise actionable sentence. Use an empty array when there is nothing.
- Report ALL findings in one pass: keep examining the remaining evidence after the first few; never stop early or list only examples.

CONVERGENCE
- Find everything in ONE pass and batch every owner decision into the first review — never dribble out new findings or escalations pass after pass.
- On re-review (the report carries ## Follow-up Validation sections from prior cycles): judge only (a) whether each prior finding is now evidenced, and (b) whether the corrections introduced a new problem. Do not open new fronts on long-standing content. Never re-raise an item the follow-ups resolved.
- The plan's decisions are settled: verify the implementation against the plan's stated approach — do not second-guess approach choices, propose redesigns, or demand a different implementation of agreed behavior.
- Calibrate to the owner's bar: if the recorded evidence shows the deliverable working as specified, approve it. Report a finding only if the owner would plausibly block the deliverable over it. When torn between flagging and passing, pass.

EVIDENCE RIGOR
- Procedures must actually establish what they claim: finding one expected value in a config file does not prove the whole file is unchanged; an ignored file's absence from git status does not prove it was preserved; a successful build does not prove UI rendering.
- For root .env preservation, use trustworthy baseline evidence (a hash, diff, or status recorded before execution) when the report contains it. Otherwise distinguish "current configuration confirmed, no secrets exposed" from "proven never modified" — claim only what the evidence supports and say what the stronger claim would need. Never print, log, or expose secret values.
- If a requirement cannot be conclusively verified, status NOT_VERIFIED with the limitation stated — never PASS.

DELEGATE_PROMPT
- A single complete ready-to-copy prompt (one string) covering ALL outstanding checks Muse can reasonably perform: missing tests, database behavior, file/convention inspection, documentation commands, configuration and secret hygiene, and browser checks where automation may be available. Empty string when nothing is delegable.
- The prompt must: identify the deliverable and give the exact plan, execution report, and review file paths stated in this task; list each outstanding check with what constitutes success; authorize running tests, inspecting files, starting and stopping temporary servers, and using available browser automation; require recording actual commands, results, and supporting evidence; require appending the results under a new "## Follow-up Validation" section at the end of the existing execution report while preserving its original contents; prohibit application-code fixes, unrelated changes, and commits; require reporting failures and unavailable capabilities instead of inventing success; and forbid rerunning validations already marked PASS except to investigate a genuine contradiction.
- If a check is only partially automatable, include the automatable part here and instruct Muse to report the limitation plus the specific human fallback needed. For browser-automation checks in particular, spell out the exact human fallback steps Muse must report if automation is unavailable or insufficient to establish the result.
- Format the prompt for readability: a short intro (deliverable, paths, authorization, standing rules), then numbered validation tasks each with its procedure and success criterion, then a clear closing (how to record evidence, append under ## Follow-up Validation preserving the original, report failures and limitations). Separate the parts with blank lines. Never emit a single dense paragraph.
- Inside the prompt, use inline code or ``` fenced blocks for commands (never ```` fences: the prompt itself is wrapped in one).

HUMAN_CHECKS
- Include ONLY checks that genuinely require the owner: visual or usability judgments that cannot be reliably automated, actions needing access Muse lacks, or checks browser automation cannot complete. Delegate first — do not assign work to the owner merely because the plan calls it "manual". Never duplicate a check assigned to Muse (including browser checks): conditional human fallbacks belong in the delegate prompt, and an unconditional human check is allowed only when the requirement needs human judgment even after Muse records its evidence. Each entry: check (what), where (directory or environment), steps (ordered actions), expected (exact observable result), cleanup (server/temp-file cleanup; empty string when none applies). Use an empty array when nothing remains.
- Every check must be executable with no further research: each step is one action with exact commands in inline code or concrete browser actions with URLs, in execution order (a step may embed one fenced block for a multi-line command). Derive all commands, paths, flags, and APIs from the plan and report — never invent project APIs or assume an unchecked command works. Keep instructions complete but concise — no tutorials.

RULES
- Output ONLY the JSON object.
- Reason carefully but keep every string short: names under ~60 characters, notes and findings one sentence.
- Evaluate ONLY the received evidence. Never assume later work. Never claim you ran tests or inspected code."""


class ReviewError(Exception):
    """Fatal review failure (message is safe to show; never includes the key)."""


def load_config(path):
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        raise ReviewError(f"config file not found: {path}")
    except json.JSONDecodeError as e:
        raise ReviewError(f"config file is not valid JSON ({path}): {e}")
    for key in ("api_url", "model", "api_key_env", "max_output_tokens"):
        if not config.get(key):
            raise ReviewError(f"config {path} is missing required key: {key}")
    config.setdefault("temperature", 0)
    return config


def read_dotenv_value(path, name):
    """Minimal KEY=VALUE lookup for the API-key fallback. Returns "" if absent."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == name:
                    return value.strip().strip("'\"")
    except FileNotFoundError:
        pass
    return ""


def get_api_key(env_name):
    key = os.environ.get(env_name, "").strip()
    if not key:
        key = read_dotenv_value(".env", env_name)
    if not key:
        raise ReviewError(
            f"API key not found: set ${env_name} or add {env_name}=<key> to ./.env "
            "(never commit the key)"
        )
    return key


def read_input_file(label, path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise ReviewError(f"{label} file not found: {path}")
    except OSError as e:
        raise ReviewError(f"cannot read {label} file {path}: {e}")


def build_user_message(plan_path, plan_text, report_path, report_text,
                       review_path):
    return (
        "Review the following feature plan against its execution report. "
        "Output ONLY the specified JSON object.\n\n"
        f"Plan path: {plan_path}\n"
        f"Execution report path: {report_path}\n"
        f"This review will be saved to: {review_path}\n"
        "(Quote these exact paths in the delegate prompt. The report may "
        "contain appended follow-up validation sections from previously "
        "delegated checks — treat their recorded commands and outputs as "
        "evidence exactly like the original report content.)\n\n"
        f"===== BEGIN FEATURE PLAN ({plan_path}, {len(plan_text)} chars) =====\n"
        f"{plan_text}\n"
        "===== END FEATURE PLAN =====\n\n"
        f"===== BEGIN EXECUTION REPORT ({report_path}, {len(report_text)} chars) "
        "=====\n"
        f"{report_text}\n"
        "===== END EXECUTION REPORT ====="
    )


def post_chat_completion(api_url, api_key, model, max_tokens, temperature,
                         system_prompt, user_message):
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")
    request = urllib.request.Request(
        api_url, data=payload,
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request,
                                    timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:1500]
        except Exception:
            body = ""
        lowered = body.lower()
        if e.code in (400, 413) and any(
                word in lowered for word in
                ("context", "too long", "too large", "maximum", "token")):
            raise ReviewError(
                "reviewer API reports the inputs exceed the model's supported "
                f"context (HTTP {e.code}). Refusing to truncate evidence — no "
                f"review was written. Details: {body or e}"
            )
        raise ReviewError(f"reviewer API request failed (HTTP {e.code}): {body or e}")
    except urllib.error.URLError as e:
        raise ReviewError(f"reviewer API request failed (network): {e}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ReviewError(f"reviewer API returned non-JSON response: {raw[:500]}")
    try:
        choice = data["choices"][0]
        content = choice["message"].get("content")
        finish_reason = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError):
        raise ReviewError(f"reviewer API returned unexpected shape: {raw[:500]}")
    usage = data.get("usage", {})
    if finish_reason == "length":
        raise ReviewError(
            "reviewer API stopped mid-review: output token budget exhausted "
            f"(usage: {json.dumps(usage)}). The review would be truncated, so no "
            "review was written — raise max_output_tokens in the config and retry."
        )
    if not content or not content.strip():
        raise ReviewError(
            "reviewer API returned empty content "
            f"(finish_reason={finish_reason}, usage: {json.dumps(usage)}). "
            "For reasoning models this usually means max_output_tokens is too small "
            "to hold reasoning plus the review — raise max_output_tokens in the "
            "config and retry. No review was written."
        )
    print(f"reviewer usage: {json.dumps(usage)}", file=sys.stderr)
    return content.strip()


def post_anthropic_messages(api_url, api_key, model, max_tokens, temperature,
                            system_prompt, user_message):
    """Same contract as post_chat_completion via Anthropic Messages API.

    `temperature` is accepted for call compatibility but not sent: current
    Claude models manage sampling themselves (Opus 5.5 rejects it).
    """
    payload = json.dumps({
        "model": model,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
        "max_tokens": max_tokens,
    }).encode("utf-8")
    request = urllib.request.Request(
        api_url, data=payload,
        headers={"x-api-key": api_key,
                 "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request,
                                    timeout=REQUEST_TIMEOUT_SECONDS
                                    ) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:1500]
        except Exception:
            body = ""
        lowered = body.lower()
        if e.code == 400 and any(
                word in lowered for word in
                ("context", "too long", "too large", "maximum", "token")):
            raise ReviewError(
                "reviewer API reports the inputs exceed the model's supported "
                f"context (HTTP {e.code}). Refusing to truncate evidence — no "
                f"review was written. Details: {body or e}"
            )
        raise ReviewError(
            f"reviewer API request failed (HTTP {e.code}): {body or e}")
    except urllib.error.URLError as e:
        raise ReviewError(f"reviewer API request failed (network): {e}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ReviewError(f"reviewer API returned non-JSON response: {raw[:500]}")
    try:
        blocks = data["content"]
        stop_reason = data.get("stop_reason")
    except (KeyError, TypeError):
        raise ReviewError(f"reviewer API returned unexpected shape: {raw[:500]}")
    usage = data.get("usage", {})
    if stop_reason == "max_tokens":
        raise ReviewError(
            "reviewer API stopped mid-review: output token budget exhausted "
            f"(usage: {json.dumps(usage)}). The review would be truncated, so no "
            "review was written — raise max_output_tokens in the config and retry."
        )
    content = "".join(b.get("text", "") for b in blocks
                      if isinstance(b, dict) and b.get("type") == "text")
    if not content.strip():
        raise ReviewError(
            "reviewer API returned empty content "
            f"(stop_reason={stop_reason}, usage: {json.dumps(usage)}). "
            "No review was written."
        )
    print(f"reviewer usage: {json.dumps(usage)}", file=sys.stderr)
    return content.strip()


VALIDATION_STATUSES = ("PASS", "FAIL", "NOT_VERIFIED")
FILE_OPS = ("created", "modified", "removed", "renamed")


def parse_review_json(content):
    """Extract and validate the reviewer's JSON object.

    Tolerates fenced or padded output by parsing from the first '{' to the
    last '}'. Raises ReviewError on any structural problem — no review is
    written from unusable model output.
    """
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ReviewError(
            "reviewer output contained no JSON object — no review was written. "
            f"Output head: {content[:300]}"
        )
    try:
        data = json.loads(content[start:end + 1])
    except json.JSONDecodeError as e:
        raise ReviewError(
            f"reviewer output was not valid JSON ({e}) — no review was written."
        )
    if not isinstance(data, dict):
        raise ReviewError("reviewer JSON was not an object — no review was written.")
    try:
        validations = [_check_validation(v, i)
                       for i, v in enumerate(data.get("validations", []))]
        files = [_check_file_op(f, i) for i, f in enumerate(data.get("files", []))]
        attention = [_check_finding(a, i)
                     for i, a in enumerate(data.get("needs_attention", []))]
        human = [_check_manual(m, i)
                 for i, m in enumerate(data.get("human_checks", []))]
    except ReviewError:
        raise
    for key in ("validations", "files", "needs_attention", "human_checks"):
        if key in data and not isinstance(data[key], list):
            raise ReviewError(
                f"reviewer JSON key '{key}' must be a list — no review was written."
            )
    delegate = data.get("delegate_prompt", "")
    if delegate is None:
        delegate = ""
    if not isinstance(delegate, str):
        raise ReviewError("reviewer JSON key 'delegate_prompt' must be a string.")
    return {"validations": validations, "files": files,
            "needs_attention": attention, "delegate_prompt": delegate.strip(),
            "human_checks": human}


def _check_validation(v, i):
    if not isinstance(v, dict):
        raise ReviewError(f"validations[{i}] must be an object.")
    status = str(v.get("status", "")).strip().upper()
    if status not in VALIDATION_STATUSES:
        raise ReviewError(
            f"validations[{i}] has invalid status '{v.get('status')}' "
            f"(must be one of {', '.join(VALIDATION_STATUSES)})."
        )
    name = str(v.get("name", "")).strip()
    if not name:
        raise ReviewError(f"validations[{i}] is missing its name.")
    return {"name": name, "status": status,
            "note": str(v.get("note", "")).strip()}


def _check_file_op(f, i):
    if not isinstance(f, dict):
        raise ReviewError(f"files[{i}] must be an object.")
    op = str(f.get("op", "")).strip().lower()
    if op not in FILE_OPS:
        raise ReviewError(
            f"files[{i}] has invalid op '{f.get('op')}' "
            f"(must be one of {', '.join(FILE_OPS)})."
        )
    path = str(f.get("path", "")).strip()
    if not path:
        raise ReviewError(f"files[{i}] is missing its path.")
    new_path = str(f.get("new_path", "")).strip()
    if op == "renamed" and not new_path:
        raise ReviewError(f"files[{i}] is a rename without new_path.")
    return {"op": op, "path": path, "new_path": new_path,
            "change_evidenced": bool(f.get("change_evidenced", False)),
            "uncertain": bool(f.get("uncertain", False)),
            "note": str(f.get("note", "")).strip()}


def _check_finding(a, i):
    if not isinstance(a, dict) or not str(a.get("finding", "")).strip():
        raise ReviewError(f"needs_attention[{i}] must have a finding.")
    return {"finding": str(a["finding"]).strip()}


def _check_manual(m, i):
    if not isinstance(m, dict) or not str(m.get("check", "")).strip():
        raise ReviewError(f"human_checks[{i}] must have a check.")
    steps = m.get("steps", [])
    if isinstance(steps, str):
        steps = [steps]
    if not isinstance(steps, list) or not steps:
        raise ReviewError(f"human_checks[{i}] must have steps.")
    steps = [str(s).strip() for s in steps]
    if not all(steps):
        raise ReviewError(f"human_checks[{i}] has an empty step.")
    expected = str(m.get("expected", "")).strip()
    if not expected:
        raise ReviewError(f"human_checks[{i}] must have an expected result.")
    return {"check": str(m["check"]).strip(),
            "where": str(m.get("where", "")).strip(),
            "steps": steps, "expected": expected,
            "cleanup": str(m.get("cleanup", "")).strip()}


def normalize_repo_path(path, repo_root):
    """Resolve a model-reported path to a project-relative path or None.

    None means unresolvable (empty, absolute outside the repo, escaping the
    repo root): such entries render as NOT VERIFIED, never as missing.
    """
    cand = (path or "").strip()
    if cand.startswith("./"):
        cand = cand[2:]
    if os.path.isabs(cand):
        try:
            cand = os.path.relpath(cand, repo_root)
        except ValueError:
            return None
    if not cand or cand == ".." or ".." in cand.replace("\\", "/").split("/"):
        return None
    return cand


def verify_files(file_ops, repo_root):
    """Verify each reported file operation against the filesystem.

    Returns result dicts in input order: {section, path, status, note} with
    section in created|modified|removed and status in EXISTS|MISSING|VERIFIED|
    NOT_VERIFIED|REMOVED|STILL_EXISTS. Renames expand to a removal entry for
    the old path plus a creation entry for the new path.
    """
    results = []
    for entry in file_ops:
        op = entry["op"]
        if op == "renamed":
            old_note = _join_notes(f"renamed to `{entry['new_path']}`", entry["note"])
            new_note = _join_notes(f"renamed from `{entry['path']}`", entry["note"])
            results.append(_verify_end(
                "removed", entry["path"], entry["uncertain"], False,
                old_note, repo_root))
            results.append(_verify_end(
                "created", entry["new_path"], entry["uncertain"], False,
                new_note, repo_root))
        else:
            results.append(_verify_end(
                op, entry["path"], entry["uncertain"], entry["change_evidenced"],
                entry["note"], repo_root))
    return results


def _join_notes(first, second):
    first, second = (first or "").strip(), (second or "").strip()
    if first and second:
        return f"{first}; {second}"
    return first or second


def _verify_end(section, path, uncertain, change_evidenced, note, repo_root):
    rel = normalize_repo_path(path, repo_root)
    display = f"`{rel}`" if rel else f"`{path.strip()}`"
    if rel is None:
        return {"section": section, "path": display, "status": "NOT_VERIFIED",
                "note": _join_notes("path could not be resolved confidently", note)}
    exists = os.path.exists(os.path.join(repo_root, rel))
    if section == "created":
        if exists:
            return {"section": section, "path": display, "status": "EXISTS",
                    "note": note if "renamed from" in note else ""}
        if uncertain:
            return {"section": section, "path": display, "status": "NOT_VERIFIED",
                    "note": _join_notes("path uncertain; nothing at stated path", note)}
        return {"section": section, "path": display, "status": "MISSING", "note": note}
    if section == "removed":
        if not exists:
            return {"section": section, "path": display, "status": "REMOVED",
                    "note": note if "renamed to" in note else ""}
        if uncertain:
            return {"section": section, "path": display, "status": "NOT_VERIFIED",
                    "note": _join_notes(
                        "path uncertain; file present at stated path", note)}
        return {"section": section, "path": display, "status": "STILL EXISTS",
                "note": note}
    # Modified: existence alone never verifies the intended change.
    if not exists:
        if uncertain:
            return {"section": section, "path": display, "status": "NOT_VERIFIED",
                    "note": _join_notes("path uncertain; nothing at stated path",
                                        note)}
        return {"section": section, "path": display, "status": "MISSING", "note": note}
    if change_evidenced:
        return {"section": section, "path": display, "status": "VERIFIED", "note": ""}
    return {"section": section, "path": display, "status": "NOT_VERIFIED",
            "note": note or "intended change not confirmed by recorded evidence"}


CORRECTION_BUDGET = 3

FOLLOW_UP_PREFIX = "## Follow-up Validation (cycle "


def parse_cycle_numbers(report_text):
    """List cycle numbers from Follow-up Validation sections.

    Numbered `## Follow-up Validation (cycle N)` sections contribute N; a
    legacy unnumbered `## Follow-up Validation` section counts as cycle 1.
    """
    numbers = []
    legacy = False
    for line in report_text.splitlines():
        stripped = line.strip()
        if stripped == "## Follow-up Validation":
            legacy = True
        elif (stripped.startswith(FOLLOW_UP_PREFIX)
                and stripped.endswith(")")):
            try:
                numbers.append(int(stripped[len(FOLLOW_UP_PREFIX):-1]))
            except ValueError:
                continue
    if legacy and 1 not in numbers:
        numbers.append(1)
    return sorted(numbers)


def loop_state(report_text, run_start=None):
    """Per-invocation correction budget derived from follow-up sections.

    run_start is the cycles_total observed at invocation start (None means
    this query starts the run). Historical sections never consume the
    current run's budget: only sections added since run_start count.
    """
    numbers = parse_cycle_numbers(report_text)
    total = len(numbers)
    if run_start is None:
        run_start = total
    used = max(0, total - run_start)
    return {"cycles_total": total,
            "corrections_used": used,
            "corrections_remaining": max(0, CORRECTION_BUDGET - used),
            "next_cycle_number": (max(numbers) + 1) if numbers else 1}


def compute_overall(validations, file_results, needs_attention):
    """PASS only when everything is evidenced; FAIL on demonstrated failure."""
    if any(v["status"] == "FAIL" for v in validations):
        return "FAIL"
    if any(r["status"] in ("MISSING", "STILL EXISTS") for r in file_results):
        return "FAIL"
    if any(v["status"] == "NOT_VERIFIED" for v in validations):
        return "NOT_VERIFIED"
    if any(r["status"] == "NOT_VERIFIED" for r in file_results):
        return "NOT_VERIFIED"
    if needs_attention:
        return "NOT_VERIFIED"
    return "PASS"


EMOJI = {"PASS": "\u2705", "FAIL": "\u274c", "NOT_VERIFIED": "\u26a0\ufe0f",
         "EXISTS": "\u2705", "MISSING": "\u274c", "VERIFIED": "\u2705",
         "REMOVED": "\u2705", "STILL EXISTS": "\u274c"}

SECTION_TITLES = {"created": "Files Created", "modified": "Files Modified",
                  "removed": "Files Removed"}


def render_review(overall, validations, file_results, needs_attention, human,
                  delegate_prompt, provenance):
    lines = [f"Overall: {EMOJI[overall]} {overall}", ""]
    if validations:
        lines.append("### Validations")
        lines.append("")
        for v in validations:
            line = f"- {EMOJI[v['status']]} **{v['status']}** | {v['name']}"
            if v["note"]:
                line += f": {v['note']}"
            lines.append(line)
        lines.append("")
    for section in ("created", "modified", "removed"):
        entries = [r for r in file_results if r["section"] == section]
        if not entries:
            continue
        lines.append(f"### {SECTION_TITLES[section]}")
        lines.append("")
        for r in entries:
            line = f"- {EMOJI[r['status']]} **{r['status']}** | {r['path']}"
            if r["note"]:
                line += f": {r['note']}"
            lines.append(line)
        lines.append("")
    if needs_attention:
        lines.append("### Needs Attention")
        lines.append("")
        for a in needs_attention:
            lines.append(f"- {a['finding']}")
        lines.append("")
    if delegate_prompt:
        lines.append("### Give to Muse")
        lines.append("")
        lines.append("Copy the prompt below into a new Muse session as-is:")
        lines.append("")
        lines.append("````")
        lines.append(delegate_prompt.strip())
        lines.append("````")
        lines.append("")
    lines.append("### Your Manual Checks")
    lines.append("")
    if human:
        for m in human:
            line = f"- **{m['check']}**"
            if m["where"]:
                line += f" — from `{m['where']}`"
            lines.append(line)
            for n, step in enumerate(m["steps"], 1):
                step_lines = step.splitlines() or [""]
                lines.append(f"  {n}. {step_lines[0]}")
                for cont in step_lines[1:]:
                    lines.append(f"     {cont}" if cont.strip() else "")
            lines.append(f"  Expected: {m['expected']}")
            if m["cleanup"]:
                lines.append(f"  Cleanup: {m['cleanup']}")
    else:
        lines.append("None.")
    lines.append("")
    lines.append("---")
    lines.append(provenance)
    return "\n".join(lines).rstrip() + "\n"


def review_path_for(reviews_dir, plan_path):
    stem = os.path.splitext(os.path.basename(plan_path))[0] or "review"
    return os.path.join(reviews_dir, f"{stem}-execution-report-review.md")


def write_review_file(reviews_dir, plan_path, review_text):
    os.makedirs(reviews_dir, exist_ok=True)
    path = review_path_for(reviews_dir, plan_path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(review_text.rstrip() + "\n")
    return path


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Independent evidence review of a feature plan and "
                    "execution report (one fresh-context reviewer API call, "
                    "deterministic filesystem checks and rendering).")
    parser.add_argument("--plan", required=True, help="feature plan Markdown file")
    parser.add_argument("--report", required=True, help="execution report Markdown file")
    parser.add_argument("--config", default=DEFAULT_CONFIG,
                        help="reviewer config JSON (default: alongside this script)")
    parser.add_argument("--reviews-dir", default=DEFAULT_REVIEWS_DIR,
                        help="directory for the saved review "
                             "(default: .agents/execution-reports/reviews)")
    parser.add_argument("--final-review-path", default=None, metavar="PATH",
                        help="canonical path quoted as this review's location "
                             "in the delegate prompt (default: the actual save "
                             "path); pass the canonical reviews-dir path when "
                             "staging to a temporary directory")
    parser.add_argument("--loop-state", action="store_true",
                        help="print this run's correction budget derived from "
                             "the existing follow-up history, then exit (no "
                             "API call)")
    parser.add_argument("--run-start", type=int, default=None, metavar="N",
                        help="cycles_total observed at invocation start "
                             "(default: the current total, i.e. this query "
                             "starts the run)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    if args.loop_state:
        try:
            text = read_input_file("execution report", args.report)
        except ReviewError as e:
            print(f"review-execution: error: {e}", file=sys.stderr)
            return 1
        state = loop_state(text, args.run_start)
        for key in ("cycles_total", "corrections_used",
                    "corrections_remaining", "next_cycle_number"):
            print(f"{key}: {state[key]}")
        return 0
    try:
        config = load_config(args.config)
        api_key = get_api_key(config["api_key_env"])
        plan_text = read_input_file("plan", args.plan)
        report_text = read_input_file("execution report", args.report)
        if not plan_text.strip():
            raise ReviewError(f"plan file is empty: {args.plan}")
        if not report_text.strip():
            raise ReviewError(f"execution report file is empty: {args.report}")
        # Staged runs quote the canonical destination so the delegate prompt
        # references the permanent review path, not the temp staging dir.
        message_path = (args.final_review_path
                        or review_path_for(args.reviews_dir, args.plan))
        user_message = build_user_message(
            args.plan, plan_text, args.report, report_text, message_path)
        print(f"reviewing with {config['model']} "
              f"(plan {len(plan_text)} chars, "
              f"report {len(report_text)} chars)", file=sys.stderr)
        # The single independent reviewer call: fresh context, no history.
        provider = config.get("provider", "openai")
        if provider == "anthropic":
            post = post_anthropic_messages
        elif provider == "openai":
            post = post_chat_completion
        else:
            raise ReviewError(
                "config provider must be 'anthropic' or 'openai', "
                f"got: {provider!r}")
        content = post(
            config["api_url"], api_key, config["model"],
            config["max_output_tokens"], config["temperature"],
            SYSTEM_PROMPT, user_message)
        review = parse_review_json(content)
        file_results = verify_files(review["files"], os.path.abspath("."))
        overall = compute_overall(review["validations"], file_results,
                                  review["needs_attention"])
        sampling = ("model-managed sampling" if provider == "anthropic"
                    else f"temperature {config['temperature']}")
        provenance = (
            f"*Reviewer: `{config['model']}` via `{config['api_url']}` "
            f"(one fresh-context call, {sampling}); "
            f"plan `{args.plan}` ({len(plan_text)} chars); report `{args.report}` "
            f"({len(report_text)} chars); generated "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.*"
        )
        review_text = render_review(overall, review["validations"], file_results,
                                    review["needs_attention"],
                                    review["human_checks"],
                                    review["delegate_prompt"], provenance)
        review_path = write_review_file(args.reviews_dir, args.plan,
                                        review_text)
    except ReviewError as e:
        print(f"review-execution: error: {e}", file=sys.stderr)
        return 1
    print(f"Review report: {review_path}\n")
    print(review_text.rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
