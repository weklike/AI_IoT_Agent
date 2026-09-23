# 候选05：132例真人复核入口

自动检查不能替代人工语义结论。所有模板的reviewer、reviewed_at、success仍为null；需要实际人员逐例核对原始工具数据、回答及数据库差异。失败例同样保留并审阅。

完整说明：[复核规则](../../../../docs/real-model-review.md)。[全部实际回答](ANSWERS.md)方便阅读，但仍须打开原始JSON核对工具依据/前置run/数据库。

| 集合 | 自动检查 | 类别自动计数 | 真人状态 |
|---|---|---|---|
| baseline | 60/60 | {'状态查询': 12, '历史统计': 12, '异常分析': 12, '工单幂等': 12, '失败边界': 12} | PENDING_REVIEW |
| v2 | 72/72 | {'fleet': 12, 'knowledge': 12, 'session': 12, 'power': 12, 'lifecycle': 12, 'boundaries': 12} | PENDING_REVIEW |

## baseline

| 案例 | 自动检查 | 原始证据 |
|---|---|---|
| A01-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A01-1.json) |
| A01-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A01-2.json) |
| A01-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A01-3.json) |
| A02-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A02-1.json) |
| A02-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A02-2.json) |
| A02-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A02-3.json) |
| A03-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A03-1.json) |
| A03-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A03-2.json) |
| A03-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A03-3.json) |
| A04-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A04-1.json) |
| A04-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A04-2.json) |
| A04-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A04-3.json) |
| A05-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A05-1.json) |
| A05-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A05-2.json) |
| A05-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A05-3.json) |
| A06-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A06-1.json) |
| A06-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A06-2.json) |
| A06-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A06-3.json) |
| A07-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A07-1.json) |
| A07-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A07-2.json) |
| A07-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A07-3.json) |
| A08-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A08-1.json) |
| A08-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A08-2.json) |
| A08-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A08-3.json) |
| A09-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A09-1.json) |
| A09-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A09-2.json) |
| A09-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A09-3.json) |
| A10-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A10-1.json) |
| A10-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A10-2.json) |
| A10-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A10-3.json) |
| A11-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A11-1.json) |
| A11-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A11-2.json) |
| A11-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A11-3.json) |
| A12-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A12-1.json) |
| A12-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A12-2.json) |
| A12-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A12-3.json) |
| A13-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A13-1.json) |
| A13-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A13-2.json) |
| A13-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A13-3.json) |
| A14-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A14-1.json) |
| A14-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A14-2.json) |
| A14-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A14-3.json) |
| A15-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A15-1.json) |
| A15-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A15-2.json) |
| A15-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A15-3.json) |
| A16-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A16-1.json) |
| A16-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A16-2.json) |
| A16-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A16-3.json) |
| A17-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A17-1.json) |
| A17-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A17-2.json) |
| A17-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A17-3.json) |
| A18-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A18-1.json) |
| A18-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A18-2.json) |
| A18-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A18-3.json) |
| A19-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A19-1.json) |
| A19-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A19-2.json) |
| A19-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A19-3.json) |
| A20-1 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A20-1.json) |
| A20-2 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A20-2.json) |
| A20-3 | 通过（待语义核对） | [JSON](../real-baseline-20260923-final-05/A20-3.json) |

## v2

| 案例 | 自动检查 | 原始证据 |
|---|---|---|
| B01-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B01-1.json) |
| B01-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B01-2.json) |
| B01-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B01-3.json) |
| B02-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B02-1.json) |
| B02-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B02-2.json) |
| B02-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B02-3.json) |
| B03-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B03-1.json) |
| B03-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B03-2.json) |
| B03-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B03-3.json) |
| B04-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B04-1.json) |
| B04-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B04-2.json) |
| B04-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B04-3.json) |
| B05-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B05-1.json) |
| B05-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B05-2.json) |
| B05-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B05-3.json) |
| B06-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B06-1.json) |
| B06-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B06-2.json) |
| B06-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B06-3.json) |
| B07-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B07-1.json) |
| B07-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B07-2.json) |
| B07-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B07-3.json) |
| B08-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B08-1.json) |
| B08-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B08-2.json) |
| B08-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B08-3.json) |
| B09-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B09-1.json) |
| B09-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B09-2.json) |
| B09-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B09-3.json) |
| B10-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B10-1.json) |
| B10-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B10-2.json) |
| B10-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B10-3.json) |
| B11-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B11-1.json) |
| B11-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B11-2.json) |
| B11-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B11-3.json) |
| B12-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B12-1.json) |
| B12-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B12-2.json) |
| B12-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B12-3.json) |
| B13-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B13-1.json) |
| B13-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B13-2.json) |
| B13-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B13-3.json) |
| B14-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B14-1.json) |
| B14-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B14-2.json) |
| B14-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B14-3.json) |
| B15-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B15-1.json) |
| B15-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B15-2.json) |
| B15-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B15-3.json) |
| B16-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B16-1.json) |
| B16-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B16-2.json) |
| B16-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B16-3.json) |
| B17-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B17-1.json) |
| B17-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B17-2.json) |
| B17-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B17-3.json) |
| B18-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B18-1.json) |
| B18-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B18-2.json) |
| B18-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B18-3.json) |
| B19-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B19-1.json) |
| B19-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B19-2.json) |
| B19-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B19-3.json) |
| B20-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B20-1.json) |
| B20-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B20-2.json) |
| B20-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B20-3.json) |
| B21-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B21-1.json) |
| B21-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B21-2.json) |
| B21-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B21-3.json) |
| B22-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B22-1.json) |
| B22-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B22-2.json) |
| B22-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B22-3.json) |
| B23-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B23-1.json) |
| B23-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B23-2.json) |
| B23-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B23-3.json) |
| B24-1 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B24-1.json) |
| B24-2 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B24-2.json) |
| B24-3 | 通过（待语义核对） | [JSON](../real-v2-20260923-final-05/B24-3.json) |

## 填完后只读汇总

```bash
uv run python eval/run.py --summarize artifacts/acceptance/v2/real-baseline-20260923-final-05 --review-file artifacts/acceptance/v2/review-candidate05/baseline-review.json
uv run python eval/run_v2.py --summarize artifacts/acceptance/v2/real-v2-20260923-final-05 --review-file artifacts/acceptance/v2/review-candidate05/v2-review.json
```

另按docs/demo.md实际完成主演示，核对架构与求职草案。程序不会自动代填真人结论。
