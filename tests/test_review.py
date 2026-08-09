import json

from zotero_arxiv_daily.protocol import Paper
from zotero_arxiv_daily.utils import mark_review_json_failed, write_review_json


def test_write_review_json(tmp_path):
    paper = Paper(
        source="arxiv",
        title="Test Paper",
        authors=["Test Author"],
        abstract="Test Abstract",
        url="https://arxiv.org/abs/2512.04296",
        pdf_url="https://arxiv.org/pdf/2512.04296",
        tldr="Test TLDR",
        affiliations=["Test Affiliation"],
        score=7.5,
    )
    output = tmp_path / "review.json"

    write_review_json(
        str(output),
        [paper],
        status="ready",
        sources=["arxiv"],
        include_path=["01_当前研究语料/**"],
        max_paper_num=10,
    )

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert document["status"] == "ready"
    assert document["zotero"]["include_path"] == ["01_当前研究语料/**"]
    assert document["papers"][0]["id"] == paper.url
    assert document["papers"][0]["review"]["status"] == "pending"
    assert "review:pending" in document["papers"][0]["review"]["tags"]

    mark_review_json_failed(str(output), RuntimeError("delivery failed"))
    failed_document = json.loads(output.read_text(encoding="utf-8"))
    assert failed_document["status"] == "failed"
    assert failed_document["error"] == {
        "type": "RuntimeError",
        "message": "delivery failed",
    }
    assert failed_document["papers"][0]["id"] == paper.url
