"""Fingerprint public project sources without reading credentials or runtime volumes."""

import hashlib

from tests.support.resources import ROOT


def source_hashes():
    directories = (
        "backend",
        "simulator",
        "frontend/src",
        "frontend/scripts",
        "knowledge",
        "eval",
        "tests/support",
        "scripts",
    )
    extensions = {".py", ".sql", ".md", ".jsonl", ".ts", ".vue", ".css", ".mjs"}
    paths = {
        p
        for directory in directories
        for p in (ROOT / directory).rglob("*")
        if p.is_file() and p.suffix in extensions
    }
    paths.update(
        ROOT / p
        for p in (
            "pyproject.toml",
            "uv.lock",
            "frontend/package.json",
            "frontend/package-lock.json",
        )
    )
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)
    }


def default_contract_settings(settings):
    keys = (
        "telemetry_interval_seconds",
        "fresh_sample_max_age_seconds",
        "offline_timeout_seconds",
        "overheat_threshold_c",
        "alarm_max_sample_gap_seconds",
        "power_preview_ttl_seconds",
        "power_plan_timeout_seconds",
        "power_plan_cleanup_seconds",
        "control_ack_timeout_seconds",
        "control_verification_timeout_seconds",
        "scenario_ack_timeout_seconds",
        "db_busy_timeout_ms",
        "agent_model_timeout_seconds",
        "agent_tool_timeout_seconds",
        "agent_total_timeout_seconds",
        "agent_cleanup_timeout_seconds",
        "agent_max_model_requests",
        "agent_max_tool_calls",
    )
    values = {key: getattr(settings, key) for key in keys}
    mismatches = [
        key for key, value in values.items() if value != type(settings).model_fields[key].default
    ]
    if mismatches:
        raise ValueError("非默认验收参数：" + ", ".join(mismatches))
    return values
