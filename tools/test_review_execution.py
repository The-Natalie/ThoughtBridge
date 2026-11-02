#!/usr/bin/env python3
"""Focused tests for tools/review-execution.py (stdlib unittest only).

Covers the deterministic core: reviewer-JSON parsing/validation, path
normalization, file-operation verification against the filesystem, overall
status computation, checklist rendering, review saving (reruns replace),
and loop-state budget accounting. The live LLM call itself is exercised by
calibration runs, not here.

Run:  python3 tools/test_review_execution.py   (from the repository root)
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
                      "review-execution.py")


def load_module():
    spec = importlib.util.spec_from_file_location("review_execution", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


re = load_module()


def op(op, path, **kw):
    entry = {"op": op, "path": path, "new_path": "", "change_evidenced": False,
             "uncertain": False, "note": ""}
    entry.update(kw)
    return entry


class ParseReviewJsonTests(unittest.TestCase):
    def test_valid_minimal(self):
        parsed = re.parse_review_json(json.dumps(
            {"validations": [{"name": "Unit tests", "status": "PASS"}],
             "files": [], "needs_attention": [], "manual_verification": []}))
        self.assertEqual(parsed["validations"],
                         [{"name": "Unit tests", "status": "PASS", "note": ""}])

    def test_tolerates_fenced_output(self):
        parsed = re.parse_review_json(
            '```json\n{"validations": [], "files": []}\n```')
        self.assertEqual(parsed["files"], [])

    def test_ignores_legacy_suggestions_key(self):
        parsed = re.parse_review_json(json.dumps(
            {"validations": [],
             "suggestions": [{"suggestion": "Run a secret scan."}]}))
        self.assertNotIn("suggestions", parsed)
        self.assertEqual(parsed["validations"], [])

    def test_rejects_bad_status(self):
        with self.assertRaises(re.ReviewError):
            re.parse_review_json(json.dumps(
                {"validations": [{"name": "X", "status": "PARTIALLY_VERIFIED"}]}))

    def test_rejects_rename_without_new_path(self):
        with self.assertRaises(re.ReviewError):
            re.parse_review_json(json.dumps(
                {"files": [{"op": "renamed", "path": "a.py"}]}))

    def test_rejects_non_json(self):
        with self.assertRaises(re.ReviewError):
            re.parse_review_json("All good, no JSON here.")

    def test_manual_check_shape(self):
        parsed = re.parse_review_json(json.dumps(
            {"human_checks": [
                {"check": "Views render", "where": "frontend/",
                 "steps": ["Run `npm run dev`", "Open http://x/"],
                 "expected": "Five tabs visible", "cleanup": "Ctrl+C"}]}))
        self.assertEqual(parsed["human_checks"], [
            {"check": "Views render", "where": "frontend/",
             "steps": ["Run `npm run dev`", "Open http://x/"],
             "expected": "Five tabs visible", "cleanup": "Ctrl+C"}])

    def test_manual_check_requires_steps_and_expected(self):
        with self.assertRaises(re.ReviewError):
            re.parse_review_json(json.dumps(
                {"human_checks": [{"check": "X", "expected": "Y"}]}))
        with self.assertRaises(re.ReviewError):
            re.parse_review_json(json.dumps(
                {"human_checks": [{"check": "X", "steps": ["do it"]}]}))

    def test_delegate_prompt_string_or_empty(self):
        parsed = re.parse_review_json(json.dumps(
            {"delegate_prompt": "  Run these checks.  "}))
        self.assertEqual(parsed["delegate_prompt"], "Run these checks.")
        self.assertEqual(re.parse_review_json("{}")["delegate_prompt"], "")
        with self.assertRaises(re.ReviewError):
            re.parse_review_json(json.dumps({"delegate_prompt": ["x"]}))


class NormalizePathTests(unittest.TestCase):
    def test_relative_and_dot_slash(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(re.normalize_repo_path("a/b.py", root), "a/b.py")
            self.assertEqual(re.normalize_repo_path("./a/b.py", root), "a/b.py")

    def test_absolute_inside_repo_relativized(self):
        with tempfile.TemporaryDirectory() as root:
            inside = os.path.join(root, "a.py")
            self.assertEqual(re.normalize_repo_path(inside, root), "a.py")

    def test_unresolvable(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(re.normalize_repo_path("", root))
            self.assertIsNone(re.normalize_repo_path("/tmp/elsewhere.py", root))
            self.assertIsNone(re.normalize_repo_path("../escape.py", root))


class VerifyFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "api"))
        for rel in ("api/health.py", "main.py", "legacy.py", "new_name.py"):
            with open(os.path.join(self.root, rel), "w") as f:
                f.write("x\n")

    def tearDown(self):
        self.tmp.cleanup()

    def verify(self, entries):
        return re.verify_files(entries, self.root)

    def test_created_exists_and_missing(self):
        (exists, missing) = self.verify(
            [op("created", "api/health.py"), op("created", "api/digests.py")])
        self.assertEqual((exists["status"], missing["status"]),
                         ("EXISTS", "MISSING"))

    def test_created_uncertain_absent_is_not_verified(self):
        (result,) = self.verify(
            [op("created", "maybe/here.py", uncertain=True)])
        self.assertEqual(result["status"], "NOT_VERIFIED")

    def test_modified_needs_change_evidence(self):
        (ok, weak) = self.verify(
            [op("modified", "main.py", change_evidenced=True),
             op("modified", "main.py")])
        self.assertEqual(ok["status"], "VERIFIED")
        self.assertEqual(weak["status"], "NOT_VERIFIED")

    def test_modified_absent_is_missing(self):
        (result,) = self.verify([op("modified", "gone.py")])
        self.assertEqual(result["status"], "MISSING")

    def test_removed_absent_and_still_exists(self):
        (gone, staying) = self.verify(
            [op("removed", "old_module.py"), op("removed", "legacy.py")])
        self.assertEqual((gone["status"], staying["status"]),
                         ("REMOVED", "STILL EXISTS"))

    def test_renamed_ok_expands_to_both_ends(self):
        (old, new) = self.verify(
            [op("renamed", "old_name.py", new_path="new_name.py")])
        self.assertEqual(old["section"], "removed")
        self.assertEqual((old["status"], new["status"]), ("REMOVED", "EXISTS"))
        self.assertIn("renamed to", old["note"])
        self.assertIn("renamed from", new["note"])

    def test_renamed_old_still_exists_flagged(self):
        (old, new) = self.verify(
            [op("renamed", "legacy.py", new_path="new_name.py")])
        self.assertEqual((old["status"], new["status"]),
                         ("STILL EXISTS", "EXISTS"))

    def test_unresolvable_path_never_missing(self):
        (result,) = self.verify([op("created", "/tmp/elsewhere.py")])
        self.assertEqual(result["status"], "NOT_VERIFIED")


class OverallTests(unittest.TestCase):
    def test_matrix(self):
        p = [{"status": "PASS"}]
        self.assertEqual(re.compute_overall(p, [{"status": "EXISTS"}], []), "PASS")
        self.assertEqual(
            re.compute_overall([{"status": "FAIL"}], [], []), "FAIL")
        self.assertEqual(
            re.compute_overall(p, [{"status": "MISSING"}], []), "FAIL")
        self.assertEqual(
            re.compute_overall(p, [{"status": "STILL EXISTS"}], []), "FAIL")
        self.assertEqual(
            re.compute_overall([{"status": "NOT_VERIFIED"}], [], []),
            "NOT_VERIFIED")
        self.assertEqual(
            re.compute_overall(p, [{"status": "NOT_VERIFIED"}], []),
            "NOT_VERIFIED")
        self.assertEqual(
            re.compute_overall(p, [{"status": "EXISTS"}], [{"finding": "x"}]),
            "NOT_VERIFIED")


class RenderTests(unittest.TestCase):
    def test_checklist_shape_and_omissions(self):
        text = re.render_review(
            "NOT_VERIFIED",
            [{"name": "Unit tests: 2/2", "status": "PASS", "note": ""},
             {"name": "Rendering", "status": "NOT_VERIFIED",
              "note": "no browser check recorded"}],
            [{"section": "created", "path": "`a.py`", "status": "EXISTS",
              "note": ""}],
            [], [], "", "*prov*")
        self.assertTrue(text.startswith("Overall: \u26a0\ufe0f NOT_VERIFIED\n"))
        self.assertIn("- \u2705 **PASS** | Unit tests: 2/2\n", text)
        self.assertIn("**NOT_VERIFIED** | Rendering: no browser check recorded",
                      text)
        self.assertIn("### Files Created", text)
        self.assertNotIn("### Files Modified", text)
        self.assertNotIn("### Needs Attention", text)
        self.assertNotIn("### Give to Muse", text)
        self.assertIn("### Your Manual Checks", text)
        self.assertIn("None.", text)
        self.assertNotIn("### Suggestions", text)
        self.assertTrue(text.endswith("*prov*\n"))

    def test_manual_check_renders_where_steps_expected_cleanup(self):
        text = re.render_review(
            "NOT_VERIFIED", [], [], [],
            [{"check": "Views render", "where": "frontend/",
              "steps": ["Run `npm run dev -- --port 5173`",
                        "Open http://localhost:5173/ and click each tab"],
              "expected": "Each tab shows its placeholder view",
              "cleanup": "Stop the server with Ctrl+C"}],
            "", "*prov*")
        self.assertIn("### Your Manual Checks", text)
        self.assertIn("- **Views render** — from `frontend/`\n", text)
        self.assertIn("  1. Run `npm run dev -- --port 5173`\n", text)
        self.assertIn("  2. Open http://localhost:5173/ and click each tab\n",
                      text)
        self.assertIn("  Expected: Each tab shows its placeholder view\n", text)
        self.assertIn("  Cleanup: Stop the server with Ctrl+C\n", text)

    def test_delegate_prompt_renders_fenced_and_omits_when_empty(self):
        text = re.render_review(
            "NOT_VERIFIED", [], [], [], [], "Run these checks.", "*prov*")
        self.assertIn("### Give to Muse", text)
        self.assertIn("````\nRun these checks.\n````", text)
        empty = re.render_review(
            "PASS", [], [], [], [], "", "*prov*")
        self.assertNotIn("### Give to Muse", empty)


class FinalReviewPathTests(unittest.TestCase):
    """Staged runs quote the canonical path in the delegate prompt."""

    def run_main(self, root, extra_args, delegate_prompt):
        plan = os.path.join(root, "x-plan.md")
        report = os.path.join(root, "x-report.md")
        with open(plan, "w") as f:
            f.write("# plan\n")
        with open(report, "w") as f:
            f.write("# report\n")
        seen = {}

        def fake_post(api_url, api_key, model, max_tokens, temperature,
                      system, user):
            seen["user"] = user
            return json.dumps({"validations": [], "files": [],
                               "needs_attention": [],
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
                rc = re.main(["--plan", plan, "--report", report,
                              *extra_args])
        finally:
            (re.post_chat_completion, re.get_api_key,
             re.load_config) = orig
        return rc, seen

    def test_staged_run_quotes_canonical_path(self):
        canonical = (".agents/execution-reports/reviews/"
                     "x-plan-execution-report-review.md")
        with tempfile.TemporaryDirectory() as d:
            stage = os.path.join(d, "stage")
            rc, seen = self.run_main(
                d, ["--reviews-dir", stage,
                    "--final-review-path", canonical],
                "Follow up per " + canonical)
            self.assertEqual(rc, 0)
            self.assertIn(canonical, seen["user"])
            self.assertNotIn(stage, seen["user"])
            saved = os.path.join(
                stage, "x-plan-execution-report-review.md")
            with open(saved) as f:
                self.assertIn(canonical, f.read())

    def test_default_quotes_actual_save_path(self):
        with tempfile.TemporaryDirectory() as d:
            stage = os.path.join(d, "stage")
            rc, seen = self.run_main(d, ["--reviews-dir", stage], "")
            self.assertEqual(rc, 0)
            self.assertIn(os.path.join(
                stage, "x-plan-execution-report-review.md"), seen["user"])


class WriteReviewFileTests(unittest.TestCase):
    def test_rerun_replaces_existing_review(self):
        with tempfile.TemporaryDirectory() as d:
            first = re.write_review_file(d, "x-plan.md", "one")
            self.assertTrue(first.endswith("x-plan-execution-report-review.md"))
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
        report = os.path.join(root, "x-report.md")
        with open(plan, "w") as f:
            f.write("# plan\n")
        with open(report, "w") as f:
            f.write("# report\n")
        orig = (re.post_chat_completion, re.post_anthropic_messages,
                re.get_api_key, re.load_config)
        re.post_chat_completion = post_openai
        re.post_anthropic_messages = post_anthropic
        re.get_api_key = lambda env: "test-key"
        re.load_config = lambda path: config
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    return re.main(["--plan", plan, "--report", report,
                                    "--reviews-dir",
                                    os.path.join(root, "stage")])
        finally:
            (re.post_chat_completion, re.post_anthropic_messages,
             re.get_api_key, re.load_config) = orig

    def test_anthropic_provider_uses_messages_transport(self):
        def fail_openai(*args):
            raise AssertionError("openai transport must not be used")

        def fake_anthropic(*args):
            return json.dumps({"validations": [], "files": [],
                               "needs_attention": [], "delegate_prompt": "",
                               "human_checks": []})

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                self.run_main_with(
                    d, self.base_config(provider="anthropic"),
                    fail_openai, fake_anthropic), 0)

    def test_missing_provider_defaults_to_openai(self):
        def fake_openai(*args):
            return json.dumps({"validations": [], "files": [],
                               "needs_attention": [], "delegate_prompt": "",
                               "human_checks": []})

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
                        {"type": "text", "text": '{"validations": []}'}],
            "stop_reason": "end_turn", "usage": {}})
        self.assertEqual(out, '{"validations": []}')

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


FOLLOW_UPS = """# Report

## Follow-up Validation (cycle 1)

First pass.

## Follow-up Validation (cycle 2)

Second pass.
"""


class LoopStateTests(unittest.TestCase):
    def test_no_history_starts_fresh(self):
        self.assertEqual(re.loop_state("# report\n", None),
                         {"cycles_total": 0, "corrections_used": 0,
                          "corrections_remaining": 3, "next_cycle_number": 1})

    def test_legacy_unnumbered_section_counts_as_cycle_1(self):
        state = re.loop_state("# R\n\n## Follow-up Validation\n\nOld.\n", 1)
        self.assertEqual((state["cycles_total"],
                          state["corrections_remaining"],
                          state["next_cycle_number"]), (1, 3, 2))

    def test_history_does_not_consume_budget(self):
        """Regression: historical sections still leave a fresh run 3 passes."""
        state = re.loop_state(FOLLOW_UPS, 2)
        self.assertEqual((state["cycles_total"], state["corrections_used"],
                          state["corrections_remaining"],
                          state["next_cycle_number"]), (2, 0, 3, 3))
        # A fresh query at invocation start also reports a full budget.
        self.assertEqual(re.loop_state(FOLLOW_UPS, None)[
            "corrections_remaining"], 3)

    def test_spend_counts_this_run_only(self):
        text = FOLLOW_UPS + "\n## Follow-up Validation (cycle 3)\n\nThird.\n"
        state = re.loop_state(text, 2)
        self.assertEqual((state["corrections_used"],
                          state["corrections_remaining"],
                          state["next_cycle_number"]), (1, 2, 4))

    def test_budget_exhausted_after_three_passes(self):
        text = FOLLOW_UPS
        for n in (3, 4, 5):
            text += f"\n## Follow-up Validation (cycle {n})\n\nPass {n}.\n"
        state = re.loop_state(text, 2)
        self.assertEqual((state["corrections_used"],
                          state["corrections_remaining"]), (3, 0))

    def test_ignores_malformed_sections(self):
        text = FOLLOW_UPS + "\n## Follow-up Validation (cycle soon)\n\nX.\n"
        text += "\n## Follow-up Validation notes\n\nY.\n"
        self.assertEqual(re.parse_cycle_numbers(text), [1, 2])

    def test_loop_state_cli(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "x-plan.md")
            report = os.path.join(d, "x-report.md")
            with open(plan, "w") as f:
                f.write("# plan\n")
            with open(report, "w") as f:
                f.write(FOLLOW_UPS)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = re.main(["--loop-state", "--plan", plan,
                              "--report", report, "--run-start", "0"])
            self.assertEqual(rc, 0)
            self.assertEqual(
                out.getvalue(),
                "cycles_total: 2\ncorrections_used: 2\n"
                "corrections_remaining: 1\nnext_cycle_number: 3\n")

    def test_loop_state_cli_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "x-plan.md")
            with open(plan, "w") as f:
                f.write("# plan\n")
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(
                        re.main(["--loop-state", "--plan", plan,
                                 "--report", "/nonexistent-report.md"]), 1)


class PromptCalibrationTests(unittest.TestCase):
    """Pin the anti-nitpick and convergence rules in the reviewer prompt."""

    def test_convergence_rules_present(self):
        self.assertIn("never dribble out new findings", re.SYSTEM_PROMPT)
        self.assertIn("Never re-raise an item the follow-ups resolved",
                      re.SYSTEM_PROMPT)

    def test_owner_bar_and_settled_decisions_present(self):
        self.assertIn("would plausibly block the deliverable",
                      re.SYSTEM_PROMPT)
        self.assertIn("do not second-guess approach choices",
                      re.SYSTEM_PROMPT)
        self.assertIn("never to polish an already convincing record",
                      re.SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
