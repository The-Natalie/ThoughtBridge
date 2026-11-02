#!/usr/bin/env python3
"""Focused tests for tools/review-plan.py (stdlib unittest only).

Covers the deterministic core: reviewer-JSON parsing/validation, plan
structure checks, overall status computation, checklist rendering, review
saving (reruns replace), and loop-state budget accounting. The live LLM
call itself is exercised by calibration runs, not here.

Run:  python3 tools/test_review_plan.py   (from the repository root)
"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.request

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "review-plan.py")


def load_module():
    spec = importlib.util.spec_from_file_location("review_plan", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


re = load_module()


def full_plan(**overrides):
    """Minimal plan containing every required template section."""
    sections = {
        "Feature Description": "Ship the thing.",
        "User Story": "As a user I want it.",
        "Problem Statement": "The problem.",
        "Scope": "- In scope: A\n- Out of scope: B",
        "Solution Statement": "The approach.",
        "Feature Metadata": "**Feature Type**: New Capability",
        "CONTEXT REFERENCES": "None yet.",
        "IMPLEMENTATION PLAN": "Phase 1: build it.",
        "STEP-BY-STEP TASKS": (
            "### Task Format Guidelines\n\n"
            "Use keywords.\n\n"
            "### CREATE a.py\n\n"
            "- **IMPLEMENT**: the thing\n"
            "- **VALIDATE**: `pytest test_a.py`\n\n"
            "### UPDATE b.py\n\n"
            "- **IMPLEMENT**: the other thing\n"
            "- **VALIDATE**: `pytest test_b.py`"
        ),
        "TESTING STRATEGY": "Unit tests.",
        "VALIDATION COMMANDS": (
            "### Level 1\n\n`ruff check .`\nExpected: exit 0, no violations"
        ),
        "MANUAL VERIFICATION CHECKLIST": (
            "- [ ] [agent] Click through: 1. open app; expected: loads\n"
            "- [ ] [human] Eyeball layout: 1. look; expected: tidy"
        ),
        "ROLLBACK CONSIDERATIONS": "Revert the commit.",
        "ACCEPTANCE CRITERIA": (
            "- [ ] Thing ships (L2 unit test test_a.py; expected: 2 passed)\n"
            "- [ ] No regressions (L1 ruff check; expected: exit 0)"
        ),
        "COMPLETION CHECKLIST": "- [ ] All tasks completed",
        "NOTES": "None.",
    }
    sections.update(overrides)
    return "\n\n".join(f"## {head}\n\n{body}"
                       for head, body in sections.items()) + "\n"


def statuses(results):
    return {r["name"]: r["status"] for r in results}


class ParseReviewJsonTests(unittest.TestCase):
    def test_valid_minimal(self):
        parsed = re.parse_review_json(json.dumps(
            {"checks": [{"name": "Goal alignment", "status": "PASS"}],
             "needs_attention": [], "escalations": [],
             "human_checks": []}))
        self.assertEqual(parsed["checks"],
                         [{"name": "Goal alignment", "status": "PASS",
                           "note": ""}])
        self.assertEqual(parsed["escalations"], [])

    def test_tolerates_fenced_output(self):
        parsed = re.parse_review_json(
            '```json\n{"checks": [], "escalations": []}\n```')
        self.assertEqual(parsed["checks"], [])

    def test_escalation_shape(self):
        parsed = re.parse_review_json(json.dumps(
            {"escalations": [{"issue": "PRD conflicts with build list."}]}))
        self.assertEqual(parsed["escalations"],
                         [{"issue": "PRD conflicts with build list."}])

    def test_rejects_bad_status(self):
        with self.assertRaises(re.ReviewError):
            re.parse_review_json(json.dumps(
                {"checks": [{"name": "X", "status": "MAYBE"}]}))

    def test_rejects_escalation_without_issue(self):
        with self.assertRaises(re.ReviewError):
            re.parse_review_json(json.dumps({"escalations": [{"note": "x"}]}))

    def test_rejects_non_json(self):
        with self.assertRaises(re.ReviewError):
            re.parse_review_json("Looks good, no JSON here.")

    def test_rejects_non_list_checks(self):
        with self.assertRaises(re.ReviewError):
            re.parse_review_json(json.dumps({"checks": {"name": "X"}}))

    def test_ignores_human_checks_key(self):
        parsed = re.parse_review_json(json.dumps(
            {"checks": [], "human_checks": [{"check": "X"}]}))
        self.assertNotIn("human_checks", parsed)
        self.assertEqual(parsed["checks"], [])

    def test_delegate_prompt_string_or_empty(self):
        parsed = re.parse_review_json(json.dumps(
            {"delegate_prompt": "  Fix the plan.  "}))
        self.assertEqual(parsed["delegate_prompt"], "Fix the plan.")
        self.assertEqual(re.parse_review_json("{}")["delegate_prompt"], "")
        with self.assertRaises(re.ReviewError):
            re.parse_review_json(json.dumps({"delegate_prompt": ["x"]}))


class StructureTests(unittest.TestCase):
    def test_full_plan_passes(self):
        self.assertEqual(
            statuses(re.check_plan_structure(full_plan())),
            {"Required sections": "PASS",
             "Tasks have validation": "PASS",
             "Validation pass signals": "PASS",
             "Acceptance criteria verifiable": "PASS",
             "Manual checks labeled": "PASS"})

    def test_guideline_subhead_is_not_a_task(self):
        results = re.check_plan_structure(full_plan())
        task = next(r for r in results if r["name"] == "Tasks have validation")
        self.assertIn("2 tasks", task["note"])

    def test_missing_section_fails_and_dependents_unverified(self):
        plan = full_plan(**{"STEP-BY-STEP TASKS": "(removed)"})
        plan = plan.replace("## STEP-BY-STEP TASKS\n\n(removed)", "")
        got = statuses(re.check_plan_structure(plan))
        self.assertEqual(got["Required sections"], "FAIL")
        self.assertEqual(got["Tasks have validation"], "NOT_VERIFIED")

    def test_task_without_validate_names_it(self):
        body = ("### CREATE a.py\n\n- **IMPLEMENT**: x\n"
                "- **VALIDATE**: `pytest`\n\n"
                "### UPDATE b.py\n\n- **IMPLEMENT**: y\n")
        got = re.check_plan_structure(full_plan(**{"STEP-BY-STEP TASKS": body}))
        task = next(r for r in got if r["name"] == "Tasks have validation")
        self.assertEqual(task["status"], "FAIL")
        self.assertIn("1/2", task["note"])
        self.assertIn("UPDATE b.py", task["note"])
        self.assertNotIn("CREATE a.py", task["note"])

    def test_no_tasks_found(self):
        got = re.check_plan_structure(
            full_plan(**{"STEP-BY-STEP TASKS": "Do the work somehow."}))
        task = next(r for r in got if r["name"] == "Tasks have validation")
        self.assertEqual((task["status"], task["note"]),
                         ("FAIL", "no step-by-step tasks found"))

    def test_missing_expected_signals(self):
        got = re.check_plan_structure(
            full_plan(**{"VALIDATION COMMANDS": "`ruff check .`"}))
        sig = next(r for r in got if r["name"] == "Validation pass signals")
        self.assertEqual(sig["status"], "FAIL")

    def test_criteria_naming_counts(self):
        named = re.check_plan_structure(full_plan())
        crit = next(r for r in named
                    if r["name"] == "Acceptance criteria verifiable")
        self.assertIn("2/2", crit["note"])
        unnamed = re.check_plan_structure(full_plan(**{
            "ACCEPTANCE CRITERIA": "- [ ] Thing ships nicely"}))
        crit = next(r for r in unnamed
                    if r["name"] == "Acceptance criteria verifiable")
        self.assertEqual(crit["status"], "FAIL")
        self.assertIn("0/1", crit["note"])

    def test_no_criteria_listed(self):
        got = re.check_plan_structure(
            full_plan(**{"ACCEPTANCE CRITERIA": "All good."}))
        crit = next(r for r in got
                    if r["name"] == "Acceptance criteria verifiable")
        self.assertEqual(crit["status"], "FAIL")

    def test_unlabeled_manual_items(self):
        got = re.check_plan_structure(full_plan(**{
            "MANUAL VERIFICATION CHECKLIST":
                "- [ ] [agent] Click: 1. open; expected: loads\n"
                "- [ ] Verify rendering works"}))
        manual = next(r for r in got if r["name"] == "Manual checks labeled")
        self.assertEqual(manual["status"], "FAIL")
        self.assertIn("1/2", manual["note"])

    def test_empty_manual_checklist(self):
        got = re.check_plan_structure(
            full_plan(**{"MANUAL VERIFICATION CHECKLIST": "Nothing manual."}))
        manual = next(r for r in got if r["name"] == "Manual checks labeled")
        self.assertEqual(manual["status"], "FAIL")

    def test_revision_history_does_not_break_sections(self):
        plan = full_plan() + "\n## Revision History\n\n### Cycle 1\n\nFixed.\n"
        self.assertEqual(
            statuses(re.check_plan_structure(plan))["Required sections"],
            "PASS")


class OptionalInputTests(unittest.TestCase):
    def test_missing_default_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            missing = os.path.join(d, "nope.md")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(re.read_optional_input("doc", missing, False),
                                 "")

    def test_missing_explicit_is_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            missing = os.path.join(d, "nope.md")
            with self.assertRaises(re.ReviewError):
                re.read_optional_input("doc", missing, True)

    def test_empty_path_is_skipped(self):
        self.assertEqual(re.read_optional_input("doc", "", True), "")
        self.assertEqual(re.read_optional_input("doc", None, False), "")


class OverallTests(unittest.TestCase):
    def p(self):
        return [{"status": "PASS"}]

    def test_matrix(self):
        self.assertEqual(re.compute_overall(self.p(), self.p(), [], []),
                         "APPROVED")
        self.assertEqual(
            re.compute_overall([{"status": "FAIL"}], self.p(), [], []),
            "NEEDS_REVISION")
        self.assertEqual(
            re.compute_overall(self.p(), [{"status": "FAIL"}], [], []),
            "NEEDS_REVISION")
        self.assertEqual(
            re.compute_overall(self.p(), self.p(), [{"finding": "x"}], []),
            "NEEDS_REVISION")

    def test_escalations_win_over_failures(self):
        self.assertEqual(
            re.compute_overall([{"status": "FAIL"}], [{"status": "FAIL"}],
                               [{"finding": "x"}], [{"issue": "decide Y"}]),
            "NEEDS_DECISION")

    def test_unverified_blocks_approval(self):
        self.assertEqual(
            re.compute_overall([{"status": "NOT_VERIFIED"}], self.p(), [], []),
            "NEEDS_DECISION")
        self.assertEqual(
            re.compute_overall(self.p(), [{"status": "NOT_VERIFIED"}], [], []),
            "NEEDS_DECISION")


class RenderTests(unittest.TestCase):
    def test_checklist_shape_and_omissions(self):
        text = re.render_review(
            "APPROVED",
            [{"name": "Required sections", "status": "PASS",
              "note": "all 16 present"}],
            [{"name": "Goal alignment", "status": "PASS", "note": ""}],
            [], [], "", "*prov*")
        self.assertTrue(text.startswith("Overall: ✅ APPROVED\n"))
        self.assertIn("### Structure", text)
        self.assertIn("- ✅ **PASS** | Required sections: all 16 present\n",
                      text)
        self.assertIn("### Checks", text)
        self.assertNotIn("### Needs Attention", text)
        self.assertNotIn("### Needs Decision", text)
        self.assertNotIn("### Give to Builder", text)
        self.assertNotIn("Manual Checks", text)
        self.assertTrue(text.endswith("*prov*\n"))

    def test_escalations_and_builder_prompt_render(self):
        text = re.render_review(
            "NEEDS_DECISION", [], [], [],
            [{"issue": "PRD conflicts with build list."}],
            "Fix the plan.", "*prov*")
        self.assertTrue(text.startswith("Overall: 🧭 NEEDS_DECISION\n"))
        self.assertIn("### Needs Decision", text)
        self.assertIn("- PRD conflicts with build list.\n", text)
        self.assertIn("### Give to Builder", text)
        self.assertIn("````\nFix the plan.\n````", text)


class FinalReviewPathTests(unittest.TestCase):
    """Staged runs quote the canonical path in the builder prompt."""

    def run_main(self, root, extra_args, delegate_prompt):
        plan = os.path.join(root, "x-plan.md")
        with open(plan, "w") as f:
            f.write("# plan\n")
        seen = {}

        def fake_post(api_url, api_key, model, max_tokens, temperature,
                      system, user):
            seen["user"] = user
            return json.dumps({"checks": [], "needs_attention": [],
                               "escalations": [],
                               "delegate_prompt": delegate_prompt,
                               "human_checks": []})

        orig = (re.post_chat_completion, re.get_api_key, re.load_config)
        re.post_chat_completion = fake_post
        re.get_api_key = lambda env: "test-key"
        re.load_config = lambda path: {"api_url": "http://x", "model": "m",
                                       "api_key_env": "K",
                                       "max_output_tokens": 1,
                                       "temperature": 0}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    rc = re.main(["--plan", plan,
                                  "--prd", "", "--prime-summary", "",
                                  *extra_args])
        finally:
            (re.post_chat_completion, re.get_api_key,
             re.load_config) = orig
        return rc, seen

    def test_staged_run_quotes_canonical_path(self):
        canonical = ".agents/plans/reviews/x-plan-plan-review.md"
        with tempfile.TemporaryDirectory() as d:
            stage = os.path.join(d, "stage")
            rc, seen = self.run_main(
                d, ["--reviews-dir", stage,
                    "--final-review-path", canonical],
                "Follow up per " + canonical)
            self.assertEqual(rc, 0)
            self.assertIn(canonical, seen["user"])
            self.assertNotIn(stage, seen["user"])
            saved = os.path.join(stage, "x-plan-plan-review.md")
            with open(saved) as f:
                self.assertIn(canonical, f.read())

    def test_default_quotes_actual_save_path(self):
        with tempfile.TemporaryDirectory() as d:
            stage = os.path.join(d, "stage")
            rc, seen = self.run_main(d, ["--reviews-dir", stage], "")
            self.assertEqual(rc, 0)
            self.assertIn(os.path.join(stage, "x-plan-plan-review.md"),
                          seen["user"])


class WriteReviewFileTests(unittest.TestCase):
    def test_rerun_replaces_existing_review(self):
        with tempfile.TemporaryDirectory() as d:
            first = re.write_review_file(d, "x-plan.md", "one")
            self.assertTrue(first.endswith("x-plan-plan-review.md"))
            self.assertEqual(open(first).read(), "one\n")
            second = re.write_review_file(d, "x-plan.md", "two")
            self.assertEqual((second, open(first).read()), (first, "two\n"))


class _FakeAnthropicResponse:
    """Minimal urlopen stand-in serving one canned Messages payload."""

    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class ProviderTests(unittest.TestCase):
    def base_config(self, **overrides):
        config = {"api_url": "http://x", "model": "m", "api_key_env": "K",
                  "max_output_tokens": 1, "temperature": 0}
        config.update(overrides)
        return config

    def run_main_with(self, root, config, post_openai, post_anthropic):
        plan = os.path.join(root, "x-plan.md")
        with open(plan, "w") as f:
            f.write("# plan\n")
        orig = (re.post_chat_completion, re.post_anthropic_messages,
                re.get_api_key, re.load_config)
        re.post_chat_completion = post_openai
        re.post_anthropic_messages = post_anthropic
        re.get_api_key = lambda env: "test-key"
        re.load_config = lambda path: config
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    return re.main(["--plan", plan, "--prd", "",
                                    "--prime-summary", "",
                                    "--reviews-dir",
                                    os.path.join(root, "stage")])
        finally:
            (re.post_chat_completion, re.post_anthropic_messages,
             re.get_api_key, re.load_config) = orig

    def test_anthropic_provider_uses_messages_transport(self):
        def fail_openai(*args):
            raise AssertionError("openai transport must not be used")

        def fake_anthropic(*args):
            return json.dumps({"checks": [], "needs_attention": [],
                               "escalations": [], "delegate_prompt": ""})

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                self.run_main_with(
                    d, self.base_config(provider="anthropic"),
                    fail_openai, fake_anthropic), 0)

    def test_missing_provider_defaults_to_openai(self):
        def fake_openai(*args):
            return json.dumps({"checks": [], "needs_attention": [],
                               "escalations": [], "delegate_prompt": ""})

        def fail_anthropic(*args):
            raise AssertionError("anthropic transport must not be used")

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                self.run_main_with(
                    d, self.base_config(), fake_openai, fail_anthropic), 0)

    def test_unknown_provider_fails(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                self.run_main_with(
                    d, self.base_config(provider="bogus"),
                    lambda *a: "", lambda *a: ""), 1)

    def call_anthropic(self, payload):
        seen = {}

        def fake_urlopen(request, timeout=None):
            seen["request"] = request
            return _FakeAnthropicResponse(payload)

        real = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                return re.post_anthropic_messages(
                    "http://x", "k", "m", 10, 0, "sys", "user"), seen
        finally:
            urllib.request.urlopen = real

    def test_anthropic_extracts_text_blocks_only(self):
        out, _ = self.call_anthropic({
            "content": [{"type": "thinking", "text": "hmm"},
                        {"type": "text", "text": '{"checks": []}'}],
            "stop_reason": "end_turn", "usage": {}})
        self.assertEqual(out, '{"checks": []}')

    def test_anthropic_request_omits_temperature(self):
        _, seen = self.call_anthropic({
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn", "usage": {}})
        body = json.loads(seen["request"].data.decode("utf-8"))
        self.assertEqual(set(body),
                         {"model", "system", "messages", "max_tokens"})
        self.assertEqual(body["messages"],
                         [{"role": "user", "content": "user"}])

    def test_anthropic_max_tokens_is_fatal(self):
        with self.assertRaises(re.ReviewError):
            self.call_anthropic({"content": [], "stop_reason": "max_tokens",
                                 "usage": {}})


HISTORY = """# Feature: X

## NOTES

None.

## Revision History

### Cycle 1

Fixed A.

### Cycle 2

Fixed B.
"""


class LoopStateTests(unittest.TestCase):
    def test_no_history_starts_fresh(self):
        self.assertEqual(re.loop_state("# plan\n", None),
                         {"cycles_total": 0, "corrections_used": 0,
                          "corrections_remaining": 3, "next_cycle_number": 1})

    def test_history_does_not_consume_budget(self):
        """Regression: 4 historical cycles still leave a fresh run 3 passes."""
        text = HISTORY + "\n### Cycle 3\n\nFixed C.\n\n### Cycle 4\n\nFixed D.\n"
        self.assertEqual(
            re.loop_state(text, 4),
            {"cycles_total": 4, "corrections_used": 0,
             "corrections_remaining": 3, "next_cycle_number": 5})
        # A fresh query at invocation start also reports a full budget.
        self.assertEqual(re.loop_state(text, None)["corrections_remaining"], 3)

    def test_spend_counts_this_run_only(self):
        text = HISTORY + "\n### Cycle 3\n\nFixed C.\n"
        state = re.loop_state(text, 2)
        self.assertEqual((state["corrections_used"],
                          state["corrections_remaining"],
                          state["next_cycle_number"]), (1, 2, 4))

    def test_budget_exhausted_after_three_passes(self):
        text = HISTORY + "\n### Cycle 3\n\nC.\n\n### Cycle 4\n\nD.\n"
        text += "\n### Cycle 5\n\nE.\n"
        state = re.loop_state(text, 2)
        self.assertEqual((state["corrections_used"],
                          state["corrections_remaining"]), (3, 0))

    def test_next_number_skips_gaps(self):
        text = "## Revision History\n\n### Cycle 1\n\nX.\n\n### Cycle 3\n\nY.\n"
        self.assertEqual(re.loop_state(text, 2)["next_cycle_number"], 4)

    def test_ignores_cycle_headings_outside_history(self):
        text = "### Cycle 9\n\nNotes.\n\n" + HISTORY
        self.assertEqual(re.parse_cycle_numbers(text), [1, 2])

    def test_ignores_malformed_cycle_headings(self):
        text = HISTORY + "\n### Cycle soon\n\nMaybe.\n"
        self.assertEqual(re.parse_cycle_numbers(text), [1, 2])

    def test_loop_state_cli(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "x-plan.md")
            with open(plan, "w") as f:
                f.write(HISTORY)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = re.main(["--loop-state", "--plan", plan,
                              "--run-start", "1"])
            self.assertEqual(rc, 0)
            self.assertEqual(
                out.getvalue(),
                "cycles_total: 2\ncorrections_used: 1\n"
                "corrections_remaining: 2\nnext_cycle_number: 3\n")

    def test_loop_state_cli_missing_file(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    re.main(["--loop-state", "--plan",
                             "/nonexistent-plan.md"]), 1)


class PromptCalibrationTests(unittest.TestCase):
    """Pin the anti-nitpick and convergence rules in the reviewer prompt."""

    def test_convergence_rules_present(self):
        self.assertIn("never dribble out new ones pass after pass",
                      re.SYSTEM_PROMPT)
        self.assertIn("Never re-raise an item recorded as addressed",
                      re.SYSTEM_PROMPT)
        self.assertIn("Converge, don't ratchet.", re.SYSTEM_PROMPT)

    def test_owner_bar_and_no_relitigation_present(self):
        self.assertIn("would plausibly block the deliverable",
                      re.SYSTEM_PROMPT)
        self.assertIn("Do not relitigate approach", re.SYSTEM_PROMPT)
        self.assertIn("When torn between flagging and passing, pass.",
                      re.SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
