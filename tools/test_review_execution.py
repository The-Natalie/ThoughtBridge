#!/usr/bin/env python3
"""Focused tests for tools/review-execution.py (stdlib unittest only).

Covers the deterministic core: reviewer-JSON parsing/validation, path
normalization, file-operation verification against the filesystem, overall
status computation, checklist rendering, and review saving (reruns replace).
The live LLM call itself is exercised by calibration runs, not here.

Run:  python3 tools/test_review_execution.py   (from the repository root)
"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
