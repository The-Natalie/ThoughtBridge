#!/usr/bin/env python3
"""Independent review of a feature plan against its requirements.

Pipeline: the plan plus requirements context (PRD, phase build list,
project summary) go to an independent reviewer model in ONE fresh-context
API call; the model returns structured JSON (assessments, actionable
findings, escalations, human checks, builder prompt); this script checks
the plan's structure deterministically, computes the overall status, and
renders a short Markdown checklist. No review is written when the model's
output is unusable.

Stdlib only. The script never modifies the plan or any context file, runs
no tests, and starts nothing. Run from the repository root.

Usage:
    python3 tools/review-plan.py --plan <plan.md>
        [--prd PRD.md] [--build-list <list.md>]
        [--prime-summary .agents/plans/prime-summary.md]

Staged (sandboxed shells): add --reviews-dir <tmpdir> --final-review-path
<canonical review path> so the builder prompt quotes the permanent path.

Reviews are saved to .agents/plans/reviews/ as
<plan-stem>-plan-review.md (no timestamps). Reruns automatically replace
the existing review for that plan; the plan itself (including any
appended ## Revision History) is never modified.

Loop budget (no API call): --loop-state --plan <plan.md> prints the
cycle total and this run's remaining corrections; pass --run-start N
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
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "review-plan.config.json")
DEFAULT_REVIEWS_DIR = os.path.join(".agents", "plans", "reviews")
REQUEST_TIMEOUT_SECONDS = 600

SYSTEM_PROMPT = """You are an independent plan reviewer — a second set of eyes on a feature implementation plan written by an AI builder. You did NOT write the plan and have NO access to the implementation environment. Your only evidence is the plan and the requirements context in the user message (requirements doc, phase build list, project summary — whichever were provided).

Compare the plan against its requirements, reason carefully, and output a SINGLE JSON object — no Markdown, no commentary, no code fences, no text before or after — with exactly these keys:

{"checks": [{"name": "...", "status": "PASS|FAIL|NOT_VERIFIED", "note": "..."}], "needs_attention": [{"finding": "..."}], "escalations": [{"issue": "..."}], "delegate_prompt": "..."}

CHECKS
- Assess every dimension that matters for a plan: goal alignment (the plan builds the deliverable the build list describes), problem definition, implementation completeness (every in-scope requirement is covered by tasks), scope discipline (no later-phase or out-of-scope work), acceptance criteria (measurable, each tied to a verifying check), validation coverage/quality (test levels, exact pass signals, edge cases, correct agent/human performer labels), prerequisites (every unbuilt dependency identified and correctly classified), and design effectiveness (the design will achieve each operational purpose the plan claims for it).
- Status rules (no other status exists): PASS means the plan adequately covers the dimension. FAIL means a concrete deficiency you can name (missing tasks, inadequate validations, contradictions, unnecessary scope). NOT_VERIFIED means the provided context is insufficient to assess the dimension — say what is missing.
- Ground every entry in the received documents. Never assume requirements that are not written. When the build list conflicts with the requirements doc, or requirements are ambiguous, that is an escalation — never silently resolve it in favor of one reading.
- Prerequisites: enumerate everything the plan depends on that is not built yet. Each belongs in this deliverable (covered by its tasks, validation, and commit) or is a separate deliverable needing its own plan, validation, and commit — FAIL when a separate-deliverable prerequisite is silently absorbed into this plan or a needed prerequisite is missing. Escalate ambiguous classifications rather than deciding them.
- Design effectiveness: judge only whether the design would plausibly fail an operational purpose the plan claims for it — a reasonable, requirement-consistent choice passes even if you would have designed it differently. Do not relitigate approach: once the plan states an approach with its rationale, that approach is settled; verify it, don't rewrite it. A foreseeable failure of purpose (a deploy-probe endpoint that reports success while dependencies are down) FAILs when routinely fixable, else escalates.
- Do not invent completion criteria the requirements never stated, and do not demand specific plan shapes beyond what the plan template requires. Omit cosmetic improvement ideas (better ways to do something already adequate). A consequential design risk — a choice whose foreseeable effects undermine a stated goal — is never an "improvement idea": FAIL it when routinely fixable, else escalate it. Calibrate to the owner's bar: report a finding only if the owner would plausibly block the deliverable over it. When torn between flagging and passing, pass.
- Keep names short ("Goal alignment", "Scope discipline", "Validation quality"). Put the key detail in note, one sentence.

NEEDS_ATTENTION
- Include ONLY concrete, actionable plan deficiencies the builder can fix without human judgment: missing tasks, inadequate validations, contradictions, unnecessary scope. Each finding concisely explains the current proposal, proposed correction, and why it matters. Use an empty array when there is nothing.
- Report ALL findings in one pass: keep examining the remaining evidence after the first few; never stop early or list only examples.

ESCALATIONS
- Include every finding that must stop the correction loop for a human decision: ambiguous or conflicting requirements; ambiguous prerequisite classifications; any correction that would affect feature scope, architecture, functionality, UX, or meaningful cost; any product or behavioral tradeoff whose readings lead to materially different outcomes; and any plan question only the owner can answer. A reasonable resolution of a minor ambiguity is accepted, not escalated. Batch every escalation into the first pass. Each issue concisely explains the current proposal, recommended choice, and why the owner must decide. Use an empty array when there is nothing.
- Never place a routine technical correction here, and never place a human decision in needs_attention.


HUMAN-FACING LANGUAGE AND HANDOFF
- Write concise plain English for a nontechnical owner. Muse is the builder/executor; the user makes owner decisions. Refer to yourself as the reviewer, never as Muse or the owner. The report identifies the configured reviewer (Claude by default); do not claim to be Claude when another provider is configured.
- For each finding or owner decision, state Current: the specific existing behavior or proposal; Proposed: your correction or recommendation; Why: the practical consequence. Keep this to 1–3 short sentences in the existing finding/issue string; quote only the relevant snippet. Do not repeat the full explanation in check notes or the handoff.
- Label findings as Routine fix or Owner decision within the existing strings, according to the existing escalation rules. For owner decisions, give a recommendation and state whether the unresolved issue blocks progress. Do not invent evidence, decisions, or approval.
- The delegate prompt addresses Muse, not the user. Include all queued routine corrections. When an owner decision exists, also include each recommended choice marked [owner approval required]; tell the user to confirm or edit these choices before copying. Do not treat a recommendation as approval. If only owner decisions remain, still provide the handoff.
- In a decision handoff, instruct Muse to apply only choices explicitly approved by the user, include queued routine corrections, record rejected choices and unresolved questions, and stop for unresolved blocking issues. Approval does not reset the correction count, authorize extra cycles, change scope permissions, or bypass review. Request a fresh review only within the existing loop rules. Never automatically proceed to /execute or /commit.
- Keep one handoff prompt, with short numbered tasks and success criteria. No repeated findings, tutorials, or ambiguous "My next action" wording.

DELEGATE_PROMPT
- A single complete ready-to-copy prompt (one string) covering ALL needs_attention corrections the builder must apply to the plan. Empty string only when neither routine corrections nor owner decisions remain.
- The prompt must: identify the plan and give the exact plan and review file paths stated in this task; list each correction with what constitutes success; authorize editing ONLY the plan file; require appending a "### Cycle N" entry under a "## Revision History" section at the end of the plan (creating the section when absent) quoting which findings were addressed, what changed, and anything not done with its reason — while preserving all prior revision entries; prohibit code changes, other files, and commits; prohibit proceeding to implementation; require reporting limitations instead of inventing coverage; and forbid silently redefining requirements — conflicting or ambiguous requirements must be escalated, never resolved by fiat.
- Format the prompt for readability: a short intro (plan, paths, authorization, standing rules), then numbered corrections each with its procedure and success criterion, then a clear closing (how to record the revision entry preserving prior entries, report limitations). Separate the parts with blank lines. Never emit a single dense paragraph.
- Inside the prompt, use inline code or ``` fenced blocks for file paths and headings (never ```` fences: the prompt itself is wrapped in one).

CONVERGENCE
- Find everything in ONE pass: checks, findings, and escalations are all batched into the first review — never dribble out new ones pass after pass.
- On re-review (the plan carries a ## Revision History from prior cycles): judge only (a) whether each prior finding was actually addressed, and (b) whether the corrections themselves introduced a new problem. Do not open new fronts on content unchanged since the last pass. Never re-raise an item recorded as addressed, and never re-raise an owner-decided escalation: settled stays settled.
- A correction that fully resolves its finding ends the matter even if a stricter reviewer could ask for more. Converge, don't ratchet.

RULES
- Output ONLY the JSON object.
- Reason carefully but keep every string short: names under ~60 characters, notes one sentence; findings at most three short sentences.
- Evaluate ONLY the received evidence. Never assume later work. The reviewer never approves its own changes: judge the plan as written, not as it might become."""


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


def read_optional_input(label, path, explicit):
    """Read a context file, or return "" when a default path is absent.

    Explicitly passed paths must exist; missing defaults are skipped with a
    stderr warning so the reviewer works in repos without that context.
    """
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        if explicit:
            raise ReviewError(f"{label} file not found: {path}")
        print(f"review-plan: warning: {label} not found ({path}), "
              f"reviewing without it", file=sys.stderr)
        return ""


def build_user_message(plan_path, plan_text, contexts, review_path):
    parts = [
        "Review the following feature plan against its requirements context. "
        "Output ONLY the specified JSON object.",
        "",
        f"Plan path: {plan_path}",
    ]
    for label, path, text in contexts:
        parts.append(f"{label} path: {path} ({len(text)} chars)")
    parts.append(f"This review will be saved to: {review_path}")
    parts.append("(Quote these exact paths in the delegate prompt. The plan may "
                "contain an appended ## Revision History from previous "
                "correction cycles — treat it as a change log and review the "
                "plan body as it now stands.)")
    parts.append("")
    parts.append(f"===== BEGIN FEATURE PLAN ({plan_path}, {len(plan_text)} "
                 f"chars) =====")
    parts.append(plan_text)
    parts.append("===== END FEATURE PLAN =====")
    for label, path, text in contexts:
        parts.append("")
        parts.append(f"===== BEGIN {label.upper()} ({path}, {len(text)} "
                     f"chars) =====")
        parts.append(text)
        parts.append(f"===== END {label.upper()} =====")
    return "\n".join(parts)


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


CHECK_STATUSES = ("PASS", "FAIL", "NOT_VERIFIED")


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
        checks = [_check_assessment(v, i)
                  for i, v in enumerate(data.get("checks", []))]
        attention = [_check_finding(a, i)
                     for i, a in enumerate(data.get("needs_attention", []))]
        escalations = [_check_escalation(s, i)
                       for i, s in enumerate(data.get("escalations", []))]
    except ReviewError:
        raise
    for key in ("checks", "needs_attention", "escalations"):
        if key in data and not isinstance(data[key], list):
            raise ReviewError(
                f"reviewer JSON key '{key}' must be a list — no review was written."
            )
    delegate = data.get("delegate_prompt", "")
    if delegate is None:
        delegate = ""
    if not isinstance(delegate, str):
        raise ReviewError("reviewer JSON key 'delegate_prompt' must be a string.")
    return {"checks": checks, "needs_attention": attention,
            "escalations": escalations,
            "delegate_prompt": delegate.strip()}


def _check_assessment(v, i):
    if not isinstance(v, dict):
        raise ReviewError(f"checks[{i}] must be an object.")
    status = str(v.get("status", "")).strip().upper()
    if status not in CHECK_STATUSES:
        raise ReviewError(
            f"checks[{i}] has invalid status '{v.get('status')}' "
            f"(must be one of {', '.join(CHECK_STATUSES)})."
        )
    name = str(v.get("name", "")).strip()
    if not name:
        raise ReviewError(f"checks[{i}] is missing its name.")
    return {"name": name, "status": status,
            "note": str(v.get("note", "")).strip()}


def _check_finding(a, i):
    if not isinstance(a, dict) or not str(a.get("finding", "")).strip():
        raise ReviewError(f"needs_attention[{i}] must have a finding.")
    return {"finding": str(a["finding"]).strip()}


def _check_escalation(s, i):
    if not isinstance(s, dict) or not str(s.get("issue", "")).strip():
        raise ReviewError(f"escalations[{i}] must have an issue.")
    return {"issue": str(s["issue"]).strip()}


# Required plan-template sections (workflow's own plan-feature template).
REQUIRED_SECTIONS = (
    "## Feature Description",
    "## User Story",
    "## Problem Statement",
    "## Scope",
    "## Solution Statement",
    "## Feature Metadata",
    "## CONTEXT REFERENCES",
    "## IMPLEMENTATION PLAN",
    "## STEP-BY-STEP TASKS",
    "## TESTING STRATEGY",
    "## VALIDATION COMMANDS",
    "## MANUAL VERIFICATION CHECKLIST",
    "## ROLLBACK CONSIDERATIONS",
    "## ACCEPTANCE CRITERIA",
    "## COMPLETION CHECKLIST",
    "## NOTES",
)

# Words indicating an acceptance criterion names its verifying check.
CHECK_REFERENCE_WORDS = ("l1", "l2", "l3", "l4", "l5", "level", "test",
                         "check", "validat", "expect")


def _split_sections(plan_text):
    """Map each `## ` heading line (stripped) to its body text."""
    sections, current, body = {}, None, []
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            if current is not None:
                sections[current] = "\n".join(body)
            current, body = stripped, []
        elif current is not None:
            body.append(line)
    if current is not None:
        sections[current] = "\n".join(body)
    return sections


def _task_blocks(tasks_body):
    """Split the step-by-step section into (heading, block) task pairs.

    `### ` headings are tasks, except the format-guidelines subhead which
    documents the task shape instead of being a task.
    """
    tasks, heading, block = [], None, []
    for line in tasks_body.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            if heading is not None and "guideline" not in heading.lower():
                tasks.append((heading, "\n".join(block)))
            heading, block = stripped[4:].strip(), []
        elif heading is not None:
            block.append(line)
    if heading is not None and "guideline" not in heading.lower():
        tasks.append((heading, "\n".join(block)))
    return tasks


def _checkbox_lines(body):
    return [ln.strip() for ln in body.splitlines()
            if ln.strip().startswith("- [ ]") or ln.strip().startswith("- [x]")
            or ln.strip().startswith("- [X]")]


def check_plan_structure(plan_text):
    """Deterministically check the plan against the plan template.

    Returns result dicts in fixed order: {name, status, note} with status in
    PASS|FAIL|NOT_VERIFIED. Semantic quality is the model reviewer's job;
    these checks only catch structural gaps a script can see reliably.
    """
    sections = _split_sections(plan_text)
    results = []

    missing = [h for h in REQUIRED_SECTIONS if h not in sections]
    if missing:
        results.append({"name": "Required sections", "status": "FAIL",
                        "note": f"missing: {', '.join(missing)}"})
    else:
        results.append({"name": "Required sections", "status": "PASS",
                        "note": f"all {len(REQUIRED_SECTIONS)} present"})

    tasks_body = sections.get("## STEP-BY-STEP TASKS")
    if tasks_body is None:
        results.append({"name": "Tasks have validation",
                        "status": "NOT_VERIFIED",
                        "note": "no step-by-step tasks section"})
    else:
        tasks = _task_blocks(tasks_body)
        if not tasks:
            results.append({"name": "Tasks have validation", "status": "FAIL",
                            "note": "no step-by-step tasks found"})
        else:
            lacking = [h for h, b in tasks if "VALIDATE" not in b]
            if lacking:
                shown = "; ".join(lacking[:3])
                more = f" (+{len(lacking) - 3} more)" if len(lacking) > 3 else ""
                results.append({"name": "Tasks have validation",
                                "status": "FAIL",
                                "note": f"{len(lacking)}/{len(tasks)} tasks "
                                        f"lack VALIDATE: {shown}{more}"})
            else:
                results.append({"name": "Tasks have validation", "status": "PASS",
                                "note": f"all {len(tasks)} tasks name validation"})

    valid_body = sections.get("## VALIDATION COMMANDS")
    if valid_body is None:
        results.append({"name": "Validation pass signals",
                        "status": "NOT_VERIFIED",
                        "note": "no validation commands section"})
    else:
        count = valid_body.count("Expected:")
        if count:
            results.append({"name": "Validation pass signals", "status": "PASS",
                            "note": f"{count} pass signals stated"})
        else:
            results.append({"name": "Validation pass signals", "status": "FAIL",
                            "note": "no Expected: pass signal stated"})

    criteria_body = sections.get("## ACCEPTANCE CRITERIA")
    if criteria_body is None:
        results.append({"name": "Acceptance criteria verifiable",
                        "status": "NOT_VERIFIED",
                        "note": "no acceptance criteria section"})
    else:
        criteria = _checkbox_lines(criteria_body)
        if not criteria:
            results.append({"name": "Acceptance criteria verifiable",
                            "status": "FAIL",
                            "note": "no acceptance criteria listed"})
        else:
            named = [c for c in criteria
                     if any(w in c.lower() for w in CHECK_REFERENCE_WORDS)]
            if not named:
                results.append({"name": "Acceptance criteria verifiable",
                                "status": "FAIL",
                                "note": f"0/{len(criteria)} criteria name a "
                                        f"verifying check"})
            else:
                results.append({"name": "Acceptance criteria verifiable",
                                "status": "PASS",
                                "note": f"{len(named)}/{len(criteria)} criteria "
                                        f"name a verifying check"})

    manual_body = sections.get("## MANUAL VERIFICATION CHECKLIST")
    if manual_body is None:
        results.append({"name": "Manual checks labeled",
                        "status": "NOT_VERIFIED",
                        "note": "no manual verification checklist"})
    else:
        items = _checkbox_lines(manual_body)
        if not items:
            results.append({"name": "Manual checks labeled", "status": "FAIL",
                            "note": "checklist is empty"})
        else:
            unlabeled = [c for c in items
                         if "agent" not in c.lower()
                         and "human" not in c.lower()]
            if unlabeled:
                shown = "; ".join(c[:60] for c in unlabeled[:2])
                results.append({"name": "Manual checks labeled", "status": "FAIL",
                                "note": f"{len(unlabeled)}/{len(items)} items "
                                        f"lack an agent/human label: {shown}"})
            else:
                results.append({"name": "Manual checks labeled", "status": "PASS",
                                "note": f"all {len(items)} items labeled"})

    return results


CORRECTION_BUDGET = 3


def parse_cycle_numbers(plan_text):
    """List the `### Cycle N` numbers in the plan's Revision History."""
    numbers = []
    in_history = False
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            in_history = stripped == "## Revision History"
        elif in_history and stripped.startswith("### Cycle "):
            try:
                numbers.append(int(stripped.split()[2]))
            except (IndexError, ValueError):
                continue
    return numbers


def loop_state(plan_text, run_start=None):
    """Per-invocation correction budget derived from revision history.

    run_start is the cycles_total observed at invocation start (None means
    this query starts the run). Historical entries never consume the
    current run's budget: only entries added since run_start count.
    """
    numbers = parse_cycle_numbers(plan_text)
    total = len(numbers)
    if run_start is None:
        run_start = total
    used = max(0, total - run_start)
    return {"cycles_total": total,
            "corrections_used": used,
            "corrections_remaining": max(0, CORRECTION_BUDGET - used),
            "next_cycle_number": (max(numbers) + 1) if numbers else 1}


def compute_overall(structure, checks, needs_attention, escalations):
    """APPROVED only when nothing needs fixing, deciding, or more evidence.

    Escalations stop the loop even when actionable findings also exist: the
    owner decides before the builder touches anything further.
    """
    if escalations:
        return "NEEDS_DECISION"
    if (any(s["status"] == "FAIL" for s in structure)
            or any(c["status"] == "FAIL" for c in checks)
            or needs_attention):
        return "NEEDS_REVISION"
    if (any(s["status"] == "NOT_VERIFIED" for s in structure)
            or any(c["status"] == "NOT_VERIFIED" for c in checks)):
        return "NEEDS_DECISION"
    return "APPROVED"


EMOJI = {"APPROVED": "✅", "NEEDS_REVISION": "🔁", "NEEDS_DECISION": "🧭",
         "PASS": "✅", "FAIL": "❌", "NOT_VERIFIED": "⚠️"}


def render_review(overall, structure, checks, needs_attention, escalations,
                  delegate_prompt, provenance):
    lines = [f"Overall: {EMOJI[overall]} {overall}", "",
             "Muse builds and executes; you decide owner questions. "
             "The configured reviewer (Claude by default) reviews the evidence; "
             "its identity is recorded below.", ""]
    if structure:
        lines.append("### Structure")
        lines.append("")
        for s in structure:
            line = f"- {EMOJI[s['status']]} **{s['status']}** | {s['name']}"
            if s["note"]:
                line += f": {s['note']}"
            lines.append(line)
        lines.append("")
    if checks:
        lines.append("### Checks")
        lines.append("")
        for v in checks:
            line = f"- {EMOJI[v['status']]} **{v['status']}** | {v['name']}"
            if v["note"]:
                line += f": {v['note']}"
            lines.append(line)
        lines.append("")
    if needs_attention:
        lines.append("### Needs Attention")
        lines.append("")
        for a in needs_attention:
            lines.append(f"- {a['finding']}")
        lines.append("")
    if escalations:
        lines.append("### Needs Decision")
        lines.append("")
        for s in escalations:
            lines.append(f"- {s['issue']}")
        lines.append("")
    if delegate_prompt:
        lines.append("### Give to Builder")
        lines.append("")
        lines.append("Confirm or edit the owner choices before copying this prompt to Muse."
                     if escalations or overall == "NEEDS_DECISION" else
                     "Muse applies these routine corrections within the existing correction limit.")
        lines.append("")
        lines.append("````")
        lines.append(delegate_prompt.strip())
        lines.append("````")
        lines.append("")
    lines.append("---")
    lines.append(provenance)
    return "\n".join(lines).rstrip() + "\n"


def review_path_for(reviews_dir, plan_path):
    stem = os.path.splitext(os.path.basename(plan_path))[0] or "review"
    return os.path.join(reviews_dir, f"{stem}-plan-review.md")


def write_review_file(reviews_dir, plan_path, review_text):
    os.makedirs(reviews_dir, exist_ok=True)
    path = review_path_for(reviews_dir, plan_path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(review_text.rstrip() + "\n")
    return path


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Independent review of a feature plan against its "
                    "requirements (one fresh-context reviewer API call, "
                    "deterministic structure checks and rendering).")
    parser.add_argument("--plan", required=True, help="feature plan Markdown file")
    parser.add_argument("--prd", default="PRD.md",
                        help="requirements doc (default: PRD.md; skipped with "
                             "a warning when absent unless explicitly passed)")
    parser.add_argument("--build-list", default=None,
                        help="phase build-list Markdown file (optional)")
    parser.add_argument("--prime-summary",
                        default=os.path.join(".agents", "plans",
                                             "prime-summary.md"),
                        help="project summary Markdown file (default: "
                             ".agents/plans/prime-summary.md; skipped with a "
                             "warning when absent unless explicitly passed)")
    parser.add_argument("--config", default=DEFAULT_CONFIG,
                        help="reviewer config JSON (default: alongside this script)")
    parser.add_argument("--reviews-dir", default=DEFAULT_REVIEWS_DIR,
                        help="directory for the saved review "
                             "(default: .agents/plans/reviews)")
    parser.add_argument("--final-review-path", default=None, metavar="PATH",
                        help="canonical path quoted as this review's location "
                             "in the builder prompt (default: the actual save "
                             "path); pass the canonical reviews-dir path when "
                             "staging to a temporary directory")
    parser.add_argument("--loop-state", action="store_true",
                        help="print this run's correction budget derived from "
                             "the existing cycle history, then exit (no API "
                             "call)")
    parser.add_argument("--run-start", type=int, default=None, metavar="N",
                        help="cycles_total observed at invocation start "
                             "(default: the current total, i.e. this query "
                             "starts the run)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    if args.loop_state:
        try:
            text = read_input_file("plan", args.plan)
        except ReviewError as e:
            print(f"review-plan: error: {e}", file=sys.stderr)
            return 1
        state = loop_state(text, args.run_start)
        for key in ("cycles_total", "corrections_used",
                    "corrections_remaining", "next_cycle_number"):
            print(f"{key}: {state[key]}")
        return 0
    raw = argv if argv is not None else sys.argv[1:]
    try:
        config = load_config(args.config)
        api_key = get_api_key(config["api_key_env"])
        plan_text = read_input_file("plan", args.plan)
        if not plan_text.strip():
            raise ReviewError(f"plan file is empty: {args.plan}")
        contexts = []
        for label, path, flag in (
                ("requirements doc", args.prd, "--prd"),
                ("build list", args.build_list, "--build-list"),
                ("project summary", args.prime_summary, "--prime-summary")):
            text = read_optional_input(label, path, flag in raw)
            if text.strip():
                contexts.append((label, path, text))
        # Staged runs quote the canonical destination so the builder prompt
        # references the permanent review path, not the temp staging dir.
        message_path = (args.final_review_path
                        or review_path_for(args.reviews_dir, args.plan))
        user_message = build_user_message(
            args.plan, plan_text, contexts, message_path)
        print(f"reviewing with {config['model']} "
              f"(plan {len(plan_text)} chars, "
              f"{len(contexts)} context files)", file=sys.stderr)
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
        structure = check_plan_structure(plan_text)
        overall = compute_overall(structure, review["checks"],
                                  review["needs_attention"],
                                  review["escalations"])
        sampling = ("model-managed sampling" if provider == "anthropic"
                    else f"temperature {config['temperature']}")
        provenance = (
            f"*Reviewer: {'Claude' if provider == 'anthropic' else 'configured independent reviewer'} "
            f"(`{config['model']}`) via `{config['api_url']}` "
            f"(one fresh-context call, {sampling}); "
            f"plan `{args.plan}` ({len(plan_text)} chars); "
        )
        if contexts:
            provenance += ("context " + ", ".join(
                f"`{p}` ({len(t)} chars)" for _, p, t in contexts) + "; ")
        else:
            provenance += "no requirements context; "
        provenance += ("generated "
                       f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.*")
        review_text = render_review(overall, structure, review["checks"],
                                    review["needs_attention"],
                                    review["escalations"],
                                    review["delegate_prompt"], provenance)
        review_path = write_review_file(args.reviews_dir, args.plan,
                                        review_text)
    except ReviewError as e:
        print(f"review-plan: error: {e}", file=sys.stderr)
        return 1
    print(f"Review report: {review_path}\n")
    print(review_text.rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
