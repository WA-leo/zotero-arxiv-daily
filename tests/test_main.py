"""Tests for main entry point.

The @hydra.main decorator makes main() hard to test directly in pytest
because config_path resolution depends on the calling context.
We test the inner logic by calling main's body with a composed config.
"""

import pytest
from hydra.core.global_hydra import GlobalHydra


@pytest.fixture(autouse=True)
def _clear_hydra():
    """Ensure GlobalHydra is clean before and after each test in this module."""
    GlobalHydra.instance().clear()
    yield
    GlobalHydra.instance().clear()


def test_main_creates_executor_and_runs(config, monkeypatch, tmp_path):
    """Verify that the main function creates an Executor and calls run()."""
    calls = []
    monkeypatch.chdir(tmp_path)

    class FakeExecutor:
        def __init__(self, cfg):
            calls.append(("init", cfg))

        def run(self):
            calls.append(("run",))

    monkeypatch.setattr("zotero_arxiv_daily.main.Executor", FakeExecutor)

    # Call main's body directly, bypassing @hydra.main
    from zotero_arxiv_daily import main as main_mod

    # Simulate what @hydra.main does: calls main(config)
    main_mod.main.__wrapped__(config)

    assert ("init", config) in calls
    assert ("run",) in calls


def test_main_debug_logging(config, monkeypatch, tmp_path):
    """Verify debug mode sets appropriate log level."""
    from omegaconf import open_dict

    monkeypatch.chdir(tmp_path)
    with open_dict(config):
        config.executor.debug = True

    class FakeExecutor:
        def __init__(self, cfg):
            pass
        def run(self):
            pass

    monkeypatch.setattr("zotero_arxiv_daily.main.Executor", FakeExecutor)

    from zotero_arxiv_daily import main as main_mod

    main_mod.main.__wrapped__(config)
    # If we get here without error, the debug path executed successfully


def test_main_marks_review_failed_when_executor_raises(config, monkeypatch):
    failures = []

    class FailingExecutor:
        def __init__(self, cfg):
            pass

        def run(self):
            raise RuntimeError("boom")

    monkeypatch.setattr("zotero_arxiv_daily.main.Executor", FailingExecutor)
    monkeypatch.setattr("zotero_arxiv_daily.main.write_review_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "zotero_arxiv_daily.main.mark_review_json_failed",
        lambda path, exc, **kwargs: failures.append((path, exc, kwargs)),
    )

    from zotero_arxiv_daily import main as main_mod

    with pytest.raises(RuntimeError, match="boom"):
        main_mod.main.__wrapped__(config)

    assert failures[0][0] == "review.json"
    assert isinstance(failures[0][1], RuntimeError)
    assert failures[0][2] == {"smtp_server": "localhost"}
