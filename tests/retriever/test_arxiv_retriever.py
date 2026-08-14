"""Tests for ArxivRetriever."""

import os
import time
from types import SimpleNamespace

import feedparser
import pytest

from zotero_arxiv_daily.retriever.arxiv_retriever import ArxivRetriever, _run_with_hard_timeout
import zotero_arxiv_daily.retriever.arxiv_retriever as arxiv_retriever


_PROCESS_TEST_TIMEOUT = 10 if os.name == "nt" else 1


def _sleep_and_return(value: str, delay_seconds: float) -> str:
    time.sleep(delay_seconds)
    return value


def _raise_runtime_error() -> None:
    raise RuntimeError("boom")


def test_arxiv_retriever(config, mock_feedparser, monkeypatch):
    monkeypatch.setattr("zotero_arxiv_daily.retriever.base.sleep", lambda _: None)

    # The RSS fixture gives us paper IDs.  After feedparser, the code calls
    # arxiv.Client().results(search) which makes real HTTP requests.  We mock
    # the arxiv Client so the test stays offline.
    new_entries = [
        e for e in mock_feedparser.entries
        if e.get("arxiv_announce_type", "new") == "new"
    ]
    paper_ids = [e.id.removeprefix("oai:arXiv.org:") for e in new_entries]

    # Build fake ArxivResult-like objects matching each RSS entry
    fake_results = []
    for entry in new_entries:
        pid = entry.id.removeprefix("oai:arXiv.org:")
        fake_results.append(SimpleNamespace(
            title=entry.title,
            authors=[SimpleNamespace(name="Test Author")],
            summary="Test abstract",
            pdf_url=f"https://arxiv.org/pdf/{pid}",
            entry_id=f"https://arxiv.org/abs/{pid}",
            source_url=lambda pid=pid: f"https://arxiv.org/e-print/{pid}",
        ))

    class FakeClient:
        def __init__(self, **kw):
            pass
        def results(self, search):
            return iter(fake_results)

    monkeypatch.setattr(arxiv_retriever.arxiv, "Client", FakeClient)

    retriever = ArxivRetriever(config)
    papers = retriever.retrieve_papers()

    assert len(papers) == len(new_entries)
    assert set(p.title for p in papers) == set(e.title for e in new_entries)
    assert all(p.full_text is None for p in papers)
    assert all(p.source_url and "/e-print/" in p.source_url for p in papers)


def test_arxiv_retriever_enriches_only_selected_paper(config, monkeypatch):
    retriever = ArxivRetriever(config)
    paper = arxiv_retriever.Paper(
        source="arxiv",
        title="Selected paper",
        authors=["Author"],
        abstract="Abstract",
        url="https://arxiv.org/abs/2608.00001",
        pdf_url="https://arxiv.org/pdf/2608.00001",
        source_url="https://arxiv.org/e-print/2608.00001",
    )
    calls = []

    def _extract_tar(source_url, paper_id, paper_title):
        calls.append((source_url, paper_id, paper_title))
        return "source text"

    monkeypatch.setattr(arxiv_retriever, "extract_text_from_tar", _extract_tar)
    monkeypatch.setattr(
        arxiv_retriever,
        "extract_text_from_html",
        lambda *args: pytest.fail("HTML fallback should not run after source extraction succeeds"),
    )

    assert retriever.enrich_paper(paper) is paper
    assert paper.full_text == "source text"
    assert calls == [(paper.source_url, paper.url, paper.title)]


def test_debug_mode_retrieves_latest_five_without_daily_rss(config, monkeypatch):
    config.executor.debug = True
    papers = [SimpleNamespace(title=f"Paper {index}") for index in range(5)]
    client_kwargs = []
    searches = []

    class FakeClient:
        def __init__(self, **kwargs):
            client_kwargs.append(kwargs)

        def results(self, search):
            searches.append(search)
            return iter(papers)

    monkeypatch.setattr(arxiv_retriever.arxiv, "Client", FakeClient)
    monkeypatch.setattr(
        arxiv_retriever.feedparser,
        "parse",
        lambda *args, **kwargs: pytest.fail("debug mode must not depend on the daily RSS feed"),
    )

    result = ArxivRetriever(config)._retrieve_raw_papers()

    assert result == papers
    assert client_kwargs == [{"page_size": 5, "num_retries": 3, "delay_seconds": 10}]
    assert searches[0].max_results == 5
    assert searches[0].sort_by == arxiv_retriever.arxiv.SortCriterion.SubmittedDate
    assert "cat:cs.AI" in searches[0].query


def test_run_with_hard_timeout_returns_value():
    result = _run_with_hard_timeout(
        _sleep_and_return,
        ("done", 0.01),
        timeout=_PROCESS_TEST_TIMEOUT,
        operation="test op",
        paper_title="paper",
    )
    assert result == "done"


def test_run_with_hard_timeout_returns_none_on_timeout(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(arxiv_retriever, "logger", SimpleNamespace(warning=warnings.append))
    result = _run_with_hard_timeout(
        _sleep_and_return, ("done", 1.0), timeout=0.01, operation="test op", paper_title="paper"
    )
    assert result is None
    assert "timed out" in warnings[0]


def test_run_with_hard_timeout_returns_none_on_failure(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(arxiv_retriever, "logger", SimpleNamespace(warning=warnings.append))
    result = _run_with_hard_timeout(
        _raise_runtime_error,
        (),
        timeout=_PROCESS_TEST_TIMEOUT,
        operation="test op",
        paper_title="paper",
    )
    assert result is None
    assert "boom" in warnings[0]
