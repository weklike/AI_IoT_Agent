"""Resolve answer markers against successful evidence supplied by this run only."""

import re

from backend.app.errors import DomainError

MARKER = re.compile(r"\[(KB|DATA):([^\[\]\s]+)\]")


def validate_references(answer: str, records: list[dict]) -> list[dict]:
    data, knowledge = {}, {}
    for record in records:
        result = record.get("result_json") or {}
        if record["status"] != "succeeded" or result.get("ok") is not True:
            continue
        identifier = record["tool_call_id"]
        data[identifier] = {"kind": "DATA", "tool_call_id": identifier}
        if record["tool_name"] == "search_fault_knowledge":
            for match in result["data"]["matches"]:
                marker = f"{match['source_id']}@{match['version']}#{match['chunk_id']}"
                knowledge.setdefault(
                    marker,
                    {
                        "kind": "KB",
                        **{key: match[key] for key in ("source_id", "version", "chunk_id", "hash")},
                        "tool_call_id": identifier,
                    },
                )
    refs, seen = [], set()
    remainder = MARKER.sub("", answer)
    if "[KB:" in remainder or "[DATA:" in remainder:
        raise DomainError("ANSWER_EVIDENCE_ERROR", "回答引用格式不完整")
    for marker in MARKER.finditer(answer):
        kind, identifier = marker.groups()
        reference = (knowledge if kind == "KB" else data).get(identifier)
        if reference is None:
            raise DomainError("ANSWER_EVIDENCE_ERROR", "回答引用不属于本次成功工具证据")
        if marker.group() not in seen:
            refs.append(reference)
            seen.add(marker.group())
    return refs
