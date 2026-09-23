"""Record public source compatibility and scan without exposing configured secrets."""
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from dotenv import dotenv_values
from scripts.acceptance import environment
from scripts.evidence import source_hashes

root = Path.cwd()
base = root / 'artifacts/acceptance/v2'
a, b = [json.loads((base / f'real-{label}-20260923-final-05/manifest.json').read_text()) for label in ('baseline', 'v2')]
checks = {key: a[key] == b[key] for key in ('source_hashes', 'prompt_sha256', 'schema_sha256', 'settings', 'model')}
checks['current_source_hashes'] = a['source_hashes'] == source_hashes()
assert all(checks.values()), checks
source = {'environment': environment(), 'source_hashes': source_hashes(), 'real_candidates': {'A_git_sha': a['environment']['git_sha'], 'B_git_sha': b['environment']['git_sha'], 'checks': checks, 'explanation': '评测启动时Git提交可包含后续文档/证据提交；逐项源码、知识、依赖锁、提示、Schema与配置摘要完全一致，当前业务源码仍一致。'}}
(base/'audit-20260923-final05/source-and-environment.json').write_text(json.dumps(source, ensure_ascii=False, indent=2)+'\n')
secrets = [v.encode() for k,v in dotenv_values('.env').items() if v and len(v)>=8 and re.search(r'key|token|secret|password', k, re.I)]
paths = [p for folder in ('backend','simulator','frontend/src','frontend/e2e','docs','eval','scripts','tests','artifacts/acceptance/v2') for p in (root/folder).rglob('*') if p.is_file() and not set(p.parts)&{'__pycache__','node_modules','.venv','.git'}]
paths += [root/'README.md']
hits = [str(p.relative_to(root)) for p in paths if any(s in p.read_bytes() for s in secrets)]
containers = subprocess.check_output(['docker','ps','--format','{{.Names}}\t{{.Ports}}'],text=True).splitlines()
owned = [s for s in containers if s.startswith(('charge-smoke-','charge-upgrade-','charge-broker-'))]
config = json.loads(subprocess.check_output(['docker','compose','--env-file','.env','-f','deploy/compose.yaml','config','--format','json'],text=True))
ports = [{'service':name,'host_ip':p.get('host_ip'),'published':p.get('published')} for name,svc in config['services'].items() for p in svc.get('ports',[])]
checks = {'all_host_ports_loopback': bool(ports) and all(p['host_ip']=='127.0.0.1' for p in ports), 'only_backend_has_model_settings': all(not [k for k in svc.get('environment',{}) if k.startswith('LLM_') and k!='LLM_MODE'] for name,svc in config['services'].items() if name!='backend'), 'frontend_has_no_model_build_args': not any(k.startswith('LLM_') for k in config['services']['frontend'].get('build',{}).get('args',{}))}
report = {'status':'PASS' if not hits and not owned and all(checks.values()) else 'FAIL','executed_at':datetime.now(UTC).isoformat(),'runtime_candidate':a['environment']['git_sha'],'scope':'只在内存比较本地敏感配置值，不输出值，不读取业务数据库；不替代所有未知凭据的通用检测。','files_scanned':len(paths),'configured_secrets_checked':len(secrets),'matching_paths':hits,'owned_test_containers_remaining':owned,'running_containers':containers,'port_bindings':ports,'compose_checks':checks}
out=base/'security-boundary-20260923-candidate05';out.mkdir(exist_ok=True);(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print({'source_checks': source['real_candidates']['checks'], 'security':report['status'],'files_scanned':len(paths),'matching_paths':hits,'owned_remaining':owned})
assert report['status']=='PASS'
