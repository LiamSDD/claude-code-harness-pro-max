import unittest

from helpers import ProjectTestCase

from agentharness.progress import Progress, ProgressError


class ProgressTests(ProjectTestCase):
    git = False

    def setUp(self):
        super().setUp()
        self.p = Progress(self.path(".claude", "harness"))

    def test_add_and_ids(self):
        a = self.p.add("Sign in")
        b = self.p.add("Sign out", steps=["click sign out"], priority=1)
        self.assertEqual((a["id"], b["id"]), (1, 2))
        self.assertEqual(self.p.features()[1]["steps"], ["click sign out"])

    def test_status_and_passes(self):
        self.p.add("Sign in")
        self.assertTrue(self.p.set_status(1, "done")["passes"])
        self.assertFalse(self.p.set_status(1, "todo")["passes"])
        with self.assertRaises(ProgressError):
            self.p.set_status(1, "finished")
        with self.assertRaises(ProgressError):
            self.p.set_status(9, "done")

    def test_next_feature_order(self):
        self.p.add("low", priority=3)
        self.p.add("high", priority=1)
        self.p.add("wip", priority=3)
        self.p.set_status(3, "in_progress")
        self.assertEqual(self.p.next_feature()["title"], "wip")
        self.p.set_status(3, "done")
        self.assertEqual(self.p.next_feature()["title"], "high")

    def test_counts(self):
        self.p.add("a")
        self.p.add("b")
        self.p.set_status(1, "done")
        c = self.p.counts()
        self.assertEqual((c["total"], c["passing"], c["done"], c["todo"]), (2, 1, 1, 1))

    def test_notes_and_tail(self):
        self.p.note("first entry")
        self.p.note("second entry", heading="Handoff", session_id="abcdef123456")
        text = self.p.tail()
        self.assertNotIn("# Progress log", text)
        self.assertIn("first entry", text)
        self.assertIn("Handoff · session abcdef12", text)
        for i in range(50):
            self.p.note(f"entry {i} " + "x" * 80)
        tail = self.p.tail(max_chars=400)
        self.assertIn("entry 49", tail)
        self.assertNotIn("first entry", tail)

    def test_header_only_log_is_empty(self):
        self.write(".claude/harness/progress.md", "# Progress log\n\nAppend-only.\n")
        self.assertEqual(self.p.tail(), "")

    def test_empty_inputs(self):
        with self.assertRaises(ProgressError):
            self.p.add("  ")
        with self.assertRaises(ProgressError):
            self.p.note("")

    def test_import_plan(self):
        plan = self.write(
            "docs/plans/p.md",
            "# Plan\n\n## Global constraints\n- [ ] not a task step\n\n### Task 1: Rate-limit logins\n\n"
            "- [ ] **Step 1: Write the failing test** for 6 attempts\n- [x] Step 2: Run it\n\n"
            "### Task 2 - Lock accounts\n- [ ] Lock after 10 failures\n\n## Notes\n- [ ] ignored\n",
        )
        added = self.p.import_plan(plan)
        self.assertEqual([f["title"] for f in added], ["Rate-limit logins", "Lock accounts"])
        self.assertEqual(added[0]["steps"], ["Write the failing test for 6 attempts", "Run it"])
        self.assertEqual(added[1]["steps"], ["Lock after 10 failures"])
        self.assertEqual(self.p.import_plan(plan), [])  # idempotent

    def test_import_plan_without_tasks(self):
        plan = self.write("p.md", "# Nothing here\n")
        with self.assertRaises(ProgressError):
            self.p.import_plan(plan)

    def test_corrupt_file(self):
        self.write(".claude/harness/features.json", "[]")
        with self.assertRaises(ProgressError):
            self.p.features()
        self.assertIn("unreadable", self.p.summary())


if __name__ == "__main__":
    unittest.main()
