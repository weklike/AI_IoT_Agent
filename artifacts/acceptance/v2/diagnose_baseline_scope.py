import asyncio,json,hashlib
from pathlib import Path
from datetime import UTC,datetime
from backend.app.config import Settings
from eval.run import evaluate
from scripts.evidence import source_hashes,default_contract_settings
from scripts.acceptance import environment

async def main():
 out=Path('artifacts/acceptance/v2/real-baseline-scope-20260923-diagnostic-08');out.mkdir(exist_ok=False)
 settings=Settings(app_env='eval',mqtt_enabled=False,llm_mode='real')
 cases=[json.loads(line) for line in Path('eval/cases.jsonl').read_text().splitlines()]
 cases=[c for c in cases if c['case_id'] in {'A09','A12','A20'}]
 m={'kind':'diagnostic','scope':'实际单台故障诊断与一般过温建议的工具范围；不可替代完整60例','executed_at':datetime.now(UTC).isoformat(),'environment':environment(),'source_hashes':source_hashes(),'settings':default_contract_settings(settings),'model':{'id':settings.llm_model,'endpoint_sha256':hashlib.sha256(settings.llm_base_url.encode()).hexdigest()},'results':[]}
 for case in cases:
  for repeat in range(1,4):
   e=await evaluate(case,repeat,settings,out);m['results'].append(e);(out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print(case['case_id'],repeat,e['automatic_pass'],flush=True)
 m['status']='PENDING_REVIEW' if all(e['automatic_pass'] for e in m['results']) else 'FAIL'
 (out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
asyncio.run(main())
