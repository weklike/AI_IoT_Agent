import json,math,statistics
from pathlib import Path
BASE=Path('artifacts/acceptance/v2')
results=[]
for label,prefix,count in [('baseline','A',60),('v2','B',72)]:
 directory=BASE/f'real-{label}-20260923-final-04'
 manifest=json.loads((directory/'manifest.json').read_text())
 records=[json.loads((directory/e['file']).read_text()) for e in manifest['results']]
 rows=[];metrics=[]
 for r in records:
  rows.append({'case_id':r['case']['case_id'],'repeat':r['repeat'],**{k:r[k] for k in ['total_seconds','model_seconds','tool_seconds']}})
  runs={x['run_id']:x for x in r.get('prelude_runs',[])+r['runs']}
  metrics.extend(m for run in runs.values() for m in run['model_metrics'])
 stats={}
 for key in ['total_seconds','model_seconds','tool_seconds']:
  values=sorted(row[key] for row in rows)
  stats[key]={'median':statistics.median(values),'p95_nearest_rank':values[math.ceil(len(values)*.95)-1]} if values else None
 valid=len(records)==count and all(all(isinstance(row[k],(int,float)) and math.isfinite(row[k]) and row[k]>=0 for k in ['total_seconds','model_seconds','tool_seconds']) for row in rows)
 results.append({'set':label,'status':'PASS' if valid else 'NOT_RUN','expected_cases':count,'observed_cases':len(records),'cases':rows,'statistics':stats,
 'model_calls':len(metrics),'calls_with_usage':sum(isinstance(m.get('usage'),dict) for m in metrics),'calls_without_usage':sum(not isinstance(m.get('usage'),dict) for m in metrics),
 'reported_total_tokens':sum(m['usage'].get('total_tokens',0) for m in metrics if isinstance(m.get('usage'),dict)),
 'usage_note':'只汇总provider实际返回的usage；超时/失败或响应缺失usage的调用单列，不补造token或声称是0消耗。未估算费用，无价格或货币结论。'})
(BASE/'model-metrics-candidate04.json').write_text(json.dumps({'status':'PASS' if all(r['status']=='PASS' for r in results) else 'NOT_RUN','results':results},ensure_ascii=False,indent=2)+'\n')
print([(r['set'],r['status'],r['observed_cases'],r['model_calls'],r['calls_without_usage']) for r in results])
