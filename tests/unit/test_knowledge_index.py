from pathlib import Path

import pytest


def test_corpus_metadata_and_deterministic_bounded_chunks():
    from backend.app.knowledge.index import load_documents, make_chunks, tokenize

    documents = load_documents(Path("knowledge"))
    assert len(documents) == 24
    assert all(document.source_kind == "authored_simulation" for document in documents)
    assert {document.applicable_model for document in documents} == {"SIM-CHG-V2"}
    chunks = make_chunks(documents[0])
    assert chunks == make_chunks(documents[0])
    assert all(len(chunk["content"]) <= 600 for chunk in chunks)
    assert "ack" in tokenize("ＡＣＫ 温度") and "温度" in tokenize("ＡＣＫ 温度")
    long = documents[0].model_copy(update={"content": "测" * 1300})
    pieces = make_chunks(long)
    assert len(pieces) == 3
    assert pieces[1]["content"][:80] == pieces[0]["content"][-80:]


def test_rejects_external_symlink_before_reading(tmp_path):
    from backend.app.knowledge.index import load_documents

    outside = tmp_path / "outside.md"
    outside.write_text("not a knowledge source")
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "escape.md").symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        load_documents(root)
