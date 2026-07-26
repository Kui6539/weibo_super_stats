"""The failure-isolation policy shared by the crawl export and reexport.

Both paths used to carry their own copy of this loop, which is how they drifted
apart -- one raised on the first locked file, the other continued. Now they
share it, so its behaviour is worth pinning down.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from core.errors import JobCancelled
from export.pipeline import RECOVERABLE_EXPORT_ERRORS, ExportTask, run_export_tasks


def ok_task(label: str, value: object = "done") -> ExportTask:
    return ExportTask(label, lambda: value, Path(f"{label}.out"))


def failing_task(label: str, err: Exception) -> ExportTask:
    def raise_it():
        raise err

    return ExportTask(label, raise_it, Path(f"{label}.out"))


class IsolationTests(unittest.TestCase):
    def test_a_locked_file_costs_only_its_own_format(self) -> None:
        outcome = run_export_tasks(
            [
                ok_task("CSV"),
                failing_task("XLSX", PermissionError("file is open in Excel")),
                ok_task("Markdown"),
            ]
        )

        self.assertEqual(outcome.failed_labels, ["XLSX"])
        self.assertEqual(outcome.results["CSV"], "done")
        self.assertEqual(outcome.results["Markdown"], "done")
        self.assertIsNone(outcome.results["XLSX"])
        self.assertTrue(outcome.any_failed)

    def test_the_warning_names_the_format_and_the_likely_cause(self) -> None:
        outcome = run_export_tasks([failing_task("XLSX", PermissionError("locked"))], action="导出")
        self.assertEqual(len(outcome.warnings), 1)
        self.assertIn("XLSX", outcome.warnings[0])
        self.assertIn("文件可能正被其他程序打开", outcome.warnings[0])
        self.assertIn("导出", outcome.warnings[0])

    def test_the_action_word_distinguishes_reexport_from_a_fresh_run(self) -> None:
        outcome = run_export_tasks([failing_task("Excel", OSError("x"))], action="重新生成")
        self.assertIn("重新生成失败", outcome.warnings[0])

    def test_a_value_error_reports_its_type_rather_than_blaming_a_lock(self) -> None:
        outcome = run_export_tasks([failing_task("CSV", ValueError("bad row"))])
        self.assertIn("ValueError", outcome.warnings[0])
        self.assertNotIn("正被其他程序打开", outcome.warnings[0])

    def test_an_unexpected_error_is_a_bug_and_propagates(self) -> None:
        with self.assertRaises(KeyError):
            run_export_tasks([failing_task("CSV", KeyError("missing"))])

    def test_cancellation_is_never_swallowed_as_an_export_failure(self) -> None:
        """A cancelled job must unwind, not be recorded as one bad format."""
        self.assertFalse(issubclass(JobCancelled, RECOVERABLE_EXPORT_ERRORS))
        with self.assertRaises(JobCancelled):
            run_export_tasks([failing_task("长图报告", JobCancelled("任务已取消。"))])

    def test_check_cancelled_runs_before_each_task_and_stops_the_run(self) -> None:
        started: list[str] = []
        calls = {"n": 0}

        def check():
            calls["n"] += 1
            if calls["n"] > 2:
                raise JobCancelled("任务已取消。")

        def track(label):
            started.append(label)
            return "done"

        tasks = [ExportTask(name, lambda name=name: track(name)) for name in ("A", "B", "C", "D")]
        with self.assertRaises(JobCancelled):
            run_export_tasks(tasks, check_cancelled=check)

        self.assertEqual(started, ["A", "B"], "no task may start after cancellation")


class CallbackTests(unittest.TestCase):
    def test_success_and_failure_callbacks_fire_once_per_task(self) -> None:
        succeeded: list[str] = []
        failed: list[tuple[str, str]] = []

        run_export_tasks(
            [ok_task("CSV"), failing_task("XLSX", OSError("locked")), ok_task("MD")],
            on_success=lambda task, value: succeeded.append(task.label),
            on_failure=lambda task, err: failed.append((task.label, type(err).__name__)),
        )

        self.assertEqual(succeeded, ["CSV", "MD"])
        self.assertEqual(failed, [("XLSX", "OSError")])

    def test_result_falls_back_when_a_task_produced_nothing(self) -> None:
        outcome = run_export_tasks([ExportTask("DOCX", lambda: None), failing_task("CSV", OSError("x"))])
        self.assertEqual(outcome.result("DOCX", []), [])
        self.assertEqual(outcome.result("CSV", []), [])
        self.assertEqual(outcome.result("missing", "fallback"), "fallback")

    def test_an_empty_task_list_is_a_clean_no_op(self) -> None:
        outcome = run_export_tasks([])
        self.assertFalse(outcome.any_failed)
        self.assertEqual(outcome.warnings, [])


if __name__ == "__main__":
    unittest.main()
