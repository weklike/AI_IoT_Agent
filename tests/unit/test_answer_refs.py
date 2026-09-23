import pytest

from backend.app.agent.references import validate_references
from backend.app.errors import DomainError


def evidence(identifier="local", name="search_fault_knowledge", ok=True):
    return {
        "tool_call_id": identifier,
        "tool_name": name,
        "status": "succeeded",
        "result_json": {
            "ok": ok,
            "data": {
                "matches": [
                    {
                        "source_id": "KB-POWER-01",
                        "version": "1.0",
                        "chunk_id": "chunk",
                        "hash": "digest",
                    }
                ]
            },
        },
    }


def test_references_record_actual_tool_and_source_once():
    refs = validate_references("[KB:KB-POWER-01@1.0#chunk] [DATA:local] [DATA:local]", [evidence()])
    assert len(refs) == 2
    assert refs[0] == {
        "kind": "KB",
        "source_id": "KB-POWER-01",
        "version": "1.0",
        "chunk_id": "chunk",
        "hash": "digest",
        "tool_call_id": "local",
    }
    assert refs[1] == {"kind": "DATA", "tool_call_id": "local"}


@pytest.mark.parametrize(
    "answer,rows",
    [
        ("[DATA:foreign]", [evidence()]),
        ("[KB:KB-POWER-01@2.0#chunk]", [evidence()]),
        ("[KB:KB-POWER-01@1.0#foreign]", [evidence()]),
        ("[KB:KB-POWER-01@1.0#chunk]", [evidence(name="get_fault_guide")]),
        ("[DATA:local]", [evidence(ok=False)]),
        ("[KB:missing]", [evidence()]),
        ("[DATA:local", [evidence()]),
    ],
)
def test_invalid_or_unearned_reference_fails(answer, rows):
    with pytest.raises(DomainError) as error:
        validate_references(answer, rows)
    assert error.value.code == "ANSWER_EVIDENCE_ERROR"


def test_legacy_plain_source_attribution_stays_compatible():
    assert validate_references("参见 GUIDE-OVERHEAT/1.0；目前没有数据。", []) == []
