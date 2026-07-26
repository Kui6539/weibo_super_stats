"""Runs a set of exporters so that one failure cannot take down the rest.

On Windows the dominant failure is mundane: the user still has last week's
weibo_posts.xlsx or weekly_report.docx open, so ``save()`` raises
PermissionError. That used to abort everything downstream -- and in the
initial-export path it went further and deleted the whole crawl on the way out,
which is precisely the situation the offline reexport exists to handle.

So each exporter runs in isolation. A failure costs that one format, records a
warning naming it, and the run continues. The caller decides what a partial
result means: the crawl marks the manifest ``export_failed`` and keeps the
cache, reexport reports which formats are missing and only raises when every
requested one failed.

Both paths funnel through here rather than each keeping its own copy of the
policy, which is how they drifted apart in the first place.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Exporter failures worth continuing past: a locked or unwritable file (OSError)
# and malformed data for one format (ValueError). Anything else is a bug and
# should surface.
RECOVERABLE_EXPORT_ERRORS = (OSError, ValueError)


@dataclass(frozen=True)
class ExportTask:
    """One export format to produce.

    ``target`` is the path to report when ``run`` returns nothing useful; some
    exporters return their path (or a list of paths), others write and return
    None.
    """

    label: str
    run: Callable[[], Any]
    target: Path | None = None


@dataclass
class ExportOutcome:
    results: dict[str, Any] = field(default_factory=dict)
    failed_labels: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def any_failed(self) -> bool:
        return bool(self.failed_labels)

    def result(self, label: str, default: Any = None) -> Any:
        value = self.results.get(label)
        return default if value is None else value


def run_export_tasks(
    tasks: list[ExportTask],
    *,
    action: str = "导出",
    check_cancelled: Callable[[], None] | None = None,
    on_success: Callable[[ExportTask, Any], None] | None = None,
    on_failure: Callable[[ExportTask, Exception], None] | None = None,
) -> ExportOutcome:
    """Run every task, isolating recoverable failures.

    ``action`` appears in the Chinese warning text ("导出" for a fresh run,
    "重新生成" for a reexport). ``check_cancelled`` runs before each task and
    is expected to raise if the user cancelled -- cancellation is not a
    recoverable export failure and must propagate.
    """
    outcome = ExportOutcome()
    for task in tasks:
        if check_cancelled is not None:
            check_cancelled()
        try:
            value = task.run()
        except RECOVERABLE_EXPORT_ERRORS as err:
            outcome.failed_labels.append(task.label)
            outcome.results[task.label] = None
            outcome.warnings.append(_failure_warning(task.label, action, err))
            if on_failure is not None:
                on_failure(task, err)
            continue
        outcome.results[task.label] = value
        if on_success is not None:
            on_success(task, value)
    return outcome


def _failure_warning(label: str, action: str, err: Exception) -> str:
    detail = "文件可能正被其他程序打开" if isinstance(err, OSError) else type(err).__name__
    return f"{label} {action}失败（{detail}），其余格式已继续生成。"
