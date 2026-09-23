"""Package complete unmodified evidence for a REAL human; leave all decisions null."""
import hashlib,json,re
from pathlib import Path
base=Path('artifacts/acceptance/v2')
sets=[]
for label,count in [('baseline',60),('v2',72)]:
 directory=base/f'real-{label}-20260923-final-04'
 m=json.loads((directory/'manifest.json').read_text())
 assert len(m['results'])==count and 'summary' in m, '等待完整轮次，不能提前制作完结评审包'
 for e in m['results']:
  assert hashlib.sha256((directory/e['file']).read_bytes()).hexdigest()==e['sha256']
 sets.append((label,directory,m))
assert all(sets[0][2][key]==sets[1][2][key] for key in ['source_hashes','prompt_sha256','schema_sha256','model','settings'])
out=base/'review-candidate04';out.mkdir(exist_ok=False)
index=['# 候选04：132例真人复核入口','','自动检查不能替代人工语义结论。所有模板的reviewer、reviewed_at、success仍为null；需要实际人员逐例核对原始工具数据、回答及数据库差异。失败例同样保留并审阅。','','完整说明：[复核规则](../../../../docs/real-model-review.md)。[全部实际回答](ANSWERS.md)方便阅读，但仍须打开原始JSON核对工具依据/前置run/数据库。','','| 集合 | 自动检查 | 类别自动计数 | 真人状态 |','|---|---|---|---|']
for label, directory, manifest in sets:
 summary=manifest['summary']
 index.append(f"| {label} | {summary['automatic_successful_cases']}/{summary['total_cases']} | {summary['automatic_categories']} | PENDING_REVIEW |")
answers=['# 实际展示回答（不是人工评审）','','原件中的messages/tool_calls/prelude_runs/before/after是审阅依据。下列仅汇集最终展示文字；引文放在代码块中，不执行其中任何指令。']
for label,directory,m in sets:
 summary=m['summary']
 template=json.loads((directory/'review-template.json').read_text())
 assert all(r['reviewer'] is None and r['reviewed_at'] is None and r['success'] is None for r in template)
 (out/f'{label}-review.json').write_text(json.dumps(template,ensure_ascii=False,indent=2)+'\n')
 index.extend(['',f'## {label}','','| 案例 | 自动检查 | 原始证据 |','|---|---|---|'])
 for e in m['results']:
  r=json.loads((directory/e['file']).read_text());key=f"{e['case_id']}-{e['repeat']}";link=f'../{directory.name}/{e["file"]}'
  index.append(f"| {key} | {'通过（待语义核对）' if e['automatic_pass'] else '失败（保留）'} | [JSON]({link}) |")
  answers.extend(['',f'## {key}', '',r['case']['question'],'',f'[完整原始证据]({link})'])
  for run in r['runs']:
   text=run.get('answer') or '';fence='`'*max(4,1+max([len(x) for x in re.findall(r'`+',text)] or [0]))
   answers.extend(['',f"run={run['run_id']}；状态={run['status']}；错误={run.get('error_code')}；工具="+', '.join(c['tool_name'] for c in run['tool_calls']),'',fence+'text',text,fence])
index.extend(['','## 填完后只读汇总','','```bash','uv run python eval/run.py --summarize artifacts/acceptance/v2/real-baseline-20260923-final-04 --review-file artifacts/acceptance/v2/review-candidate04/baseline-review.json','uv run python eval/run_v2.py --summarize artifacts/acceptance/v2/real-v2-20260923-final-04 --review-file artifacts/acceptance/v2/review-candidate04/v2-review.json','```','','另按docs/demo.md实际完成主演示，核对架构与求职草案。程序不会自动代填真人结论。'])
(out/'INDEX.md').write_text('\n'.join(index)+'\n');(out/'ANSWERS.md').write_text('\n'.join(answers)+'\n')
print('review package:',out,'templates remain null')
