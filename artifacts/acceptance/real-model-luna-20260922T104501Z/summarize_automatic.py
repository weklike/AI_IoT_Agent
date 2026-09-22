import csv
import hashlib
import json
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from backend.app.config import Settings
from scripts.acceptance import percentile

p = Path(__file__).resolve().parent
m = json.loads((p / 'manifest.json').read_text())
entries = m['results']
assert len(entries) == 60
assert {(e['case_id'], e['repeat']) for e in entries} == {(f'A{i:02}', r) for i in range(1, 21) for r in range(1, 4)}
rows, failures, metrics = [], [], []
categories, error_counts = {}, Counter()
unique_runs, unique_tools = {}, {}
for e in entries:
    path = p / e['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == e['sha256']
    r = json.loads(path.read_text())
    runs = {run['run_id']: run for run in r['runs']}
    calls = {c['tool_call_id']: c for run in runs.values() for c in run['tool_calls']}
    calls_metrics = [v for run in runs.values() for v in run['model_metrics']]
    unique_runs.update(runs)
    unique_tools.update(calls)
    metrics.extend(calls_metrics)
    errors = sorted({run['error_code'] for run in runs.values() if run['error_code']})
    error_counts.update(errors)
    category = r['case']['category']
    group = categories.setdefault(category, {'automatic_pass': 0, 'executed': 0})
    group['executed'] += 1
    group['automatic_pass'] += int(r['automatic_pass'])
    failed_checks = [k for k, v in r['automatic_checks'].items() if not v]
    if not r['automatic_pass']:
        failures.append({'case_id': e['case_id'], 'repeat': e['repeat'], 'evidence': e['file'], 'failed_checks': failed_checks, 'error_codes': errors, 'human_review': 'PENDING_REVIEW'})
    usages = [v['usage'] for v in calls_metrics if isinstance(v.get('usage'), dict) and v['usage']]
    rows.append({'case_id': e['case_id'], 'repeat': e['repeat'], 'category': category, 'automatic_pass': r['automatic_pass'], 'error_codes': '|'.join(errors), 'failed_checks': '|'.join(failed_checks), 'total_seconds': r['total_seconds'], 'model_seconds': r['model_seconds'], 'tool_seconds': r['tool_seconds'], 'unique_runs': len(runs), 'model_requests': len(calls_metrics), 'tool_calls': len(calls), 'model_requests_with_usage': len(usages), 'reported_prompt_tokens': sum(u.get('prompt_tokens', 0) for u in usages), 'reported_completion_tokens': sum(u.get('completion_tokens', 0) for u in usages), 'reported_total_tokens': sum(u.get('total_tokens', 0) for u in usages), 'human_review': 'PENDING_REVIEW', 'evidence': e['file'], 'evidence_sha256': e['sha256']})
passed = sum(r['automatic_pass'] for r in rows)
auto_meets = passed >= 54 and all(v['automatic_pass'] >= 9 for v in categories.values())
s = Settings()
report = {
    'generated_at': datetime.now(UTC).isoformat(), 'status': 'PENDING_REVIEW' if auto_meets else 'FAIL',
    'scope': 'Automatic checks and measured timing only. No human semantic or critical-error review performed.',
    'model': m['model'], 'source_commit': m['environment']['git_sha'],
    'manifest_sha256': hashlib.sha256((p / 'manifest.json').read_bytes()).hexdigest(),
    'evidence_hashes_verified': True, 'executed_cases': len(rows), 'automatic_pass_cases': passed,
    'automatic_fail_cases': len(rows) - passed, 'automatic_thresholds_met': auto_meets,
    'human_review': 'PENDING_REVIEW', 'human_success_cases': None, 'critical_error_count': None,
    'categories': categories, 'failures': failures, 'error_cases_by_code': dict(error_counts),
    'unique_agent_runs': len(unique_runs), 'model_requests': len(metrics), 'tool_calls': len(unique_tools),
    'case_metrics_seconds': {key: {'median': statistics.median(row[key] for row in rows), 'p95': percentile([row[key] for row in rows]), 'max': max(row[key] for row in rows)} for key in ('total_seconds', 'model_seconds', 'tool_seconds')},
    'percentile_method': 'nearest rank, ceil(0.95 * n); all 60 cases included, including errors and multi-run cases',
    'token_usage': {'requests_with_reported_usage': sum(bool(v.get('usage')) for v in metrics), 'requests_without_reported_usage': sum(not bool(v.get('usage')) for v in metrics), **{key: sum(row['reported_' + key] for row in rows) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}, 'note': 'Provider usage is recorded when returned. Timed-out requests may omit usage; totals are reported usage only, not an exact billed total.'},
    'cost': None, 'cost_note': 'No verified pricing supplied by the local proxy; no cost inferred.',
    'budgets': {key: getattr(s, key) for key in ('agent_model_timeout_seconds', 'agent_tool_timeout_seconds', 'agent_total_timeout_seconds', 'agent_cleanup_timeout_seconds', 'agent_max_model_requests', 'agent_max_tool_calls')},
    'isolation': 'Each case uses its own temporary SQLite and fixed data clock; MQTT disabled; normal create_app lifespan, actual API/tools/database. A15 and A16 keep setup inside each case.',
}
(p / 'automatic-metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
with (p / 'case-metrics.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
lines = ['# gpt-5.6-luna 真实模型重测', '', f'共完成 60 次案例执行，自动检查通过 {passed}/60；总体状态 {report["status"]}。人工语义与关键错误复核尚未执行，不能把自动通过数称为最终成功数。', '', '模型及参数、prompt/Schema 摘要见 manifest.json；原始案例未修改。每例隔离临时库，未向演示库写入测试工单。', '', '| 类别 | 自动通过 / 执行数 | 门槛 |', '|---|---|---|']
lines += [f'| {name} | {v["automatic_pass"]}/{v["executed"]} | ≥9/12 |' for name, v in categories.items()]
lines += ['', '| 时间指标（秒） | 中位数 | P95 | 最大值 |', '|---|---|---|---|']
lines += [f'| {key} | {v["median"]:.3f} | {v["p95"]:.3f} | {v["max"]:.3f} |' for key, v in report['case_metrics_seconds'].items()]
lines += ['', f'真实模型请求 {len(metrics)} 次，独立 Agent run {len(unique_runs)} 个，工具执行 {len(unique_tools)} 次；包含 A15/A16 案例内部的重复提交。模型请求数与 60 次案例数不同。', '', 'token 仅汇总接口实际返回的 usage，超时未返回部分不能记作零消耗；未估算费用。明细见 case-metrics.csv 和 automatic-metrics.json。', '', '## 自动失败清单', '', '| 案例 | 错误码 | 未通过检查 | 原始证据 |', '|---|---|---|---|']
lines += [f'| {f["case_id"]}-{f["repeat"]} | {", ".join(f["error_codes"]) or "无运行错误码"} | {", ".join(f["failed_checks"])} | [{f["evidence"]}]({f["evidence"]}) |' for f in failures]
lines += ['', '## 待真人复核', '', 'review-template.json 含 60 条关联原始 SHA256 的待填记录。按 docs/AI_IoT_Agent_验收规则.md 第 5 节逐例复核，填写真实 reviewer、时间、语义成功结论与关键错误；开发 Agent 没有代填。', '', '既定模型 20 秒、工具 3 秒、整轮 90 秒预算未放宽；本轮失败证据保留，不覆盖。', '']
(p / 'report.md').write_text('\n'.join(lines))
print(json.dumps({key: report[key] for key in ('status', 'executed_cases', 'automatic_pass_cases', 'categories', 'error_cases_by_code', 'unique_agent_runs', 'model_requests', 'tool_calls', 'case_metrics_seconds', 'token_usage')}, ensure_ascii=False, indent=2))

raise SystemExit(1 if report['status'] == 'FAIL' else 3)
