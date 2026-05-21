"""Unit tests for the Phase 0 background-task scaffold."""
import logging
import pytest

from fastapi import BackgroundTasks

from app.core.background import run_in_background


pytestmark = pytest.mark.unit


class _CallTracker:
    """Tiny double — records call args + lets us flip a flag to throw."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []
        self.should_raise: bool = False

    def __call__(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))
        if self.should_raise:
            raise RuntimeError("boom")


class TestRunInBackground:
    def test_registers_wrapped_callable_on_background_tasks(self):
        bg = BackgroundTasks()
        tracker = _CallTracker()
        run_in_background(bg, tracker, "x", kw="y")
        # FastAPI stores each task in BackgroundTasks.tasks (list).
        assert len(bg.tasks) == 1

    def test_callable_runs_with_args_and_kwargs_when_tasks_fire(self):
        bg = BackgroundTasks()
        tracker = _CallTracker()
        run_in_background(bg, tracker, "x", kw="y")
        # Manually invoke the underlying task — simulates FastAPI's
        # post-response background sweep.
        bg.tasks[0].func()
        assert tracker.calls == [(("x",), {"kw": "y"})]

    def test_exception_in_wrapped_callable_is_swallowed_and_logged(self, caplog):
        bg = BackgroundTasks()
        tracker = _CallTracker()
        tracker.should_raise = True
        run_in_background(bg, tracker, "x")
        with caplog.at_level(logging.ERROR):
            # Should NOT propagate — the wrapper catches and logs.
            bg.tasks[0].func()
        # And the call did happen before the throw.
        assert tracker.calls == [(("x",), {})]
        # Failure event makes it to the log.
        assert any("bg_task failed" in r.message for r in caplog.records)

    def test_success_logs_bg_task_ok_with_elapsed_ms(self, caplog):
        bg = BackgroundTasks()
        tracker = _CallTracker()
        run_in_background(bg, tracker)
        with caplog.at_level(logging.INFO):
            bg.tasks[0].func()
        ok_records = [r for r in caplog.records if "bg_task ok" in r.message]
        assert len(ok_records) == 1
        # The structured-logging extras land as attributes on the record.
        record = ok_records[0]
        assert getattr(record, "ok", None) is True
        assert isinstance(getattr(record, "elapsed_ms", None), int)
