# 模板 + 算法：研发人员人工费用分配明细表 & 汇总明细表

> 用法：工作流 B（证据链/三套资料）之"人员人工费用分配"。Agent 通过 `run_python` 查询系统库（`labor_cost` + `work_time` + `personnel`），按研发工时占比分摊人工费用，生成两张表，写入 `output/` 交付。
> 字段对应系统表：`labor_cost`（人工费用总账：工资薪酬 `total_salary`、社保 `social_insurance`、公积金 `housing_fund`、总工时 `work_hours_total`、非研发工时 `non_rd_hours`）、`work_time`（研发工时登记）、`personnel`（人员档案，`is_rd` 标识研发人员）。

---

## 一、分配算法（Agent 用 run_python 实现）

对每位研发人员、每个成本月：

```
研发工时 rd_hours = sum(work_time.hours WHERE person_id=P AND 月份=cost_month)
总工时 total   = labor_cost.work_hours_total  (当月总工时，作为分摊分母)
非研发工时     = labor_cost.non_rd_hours
研发占比 ratio  = rd_hours / total   （total 为 0 时 ratio=0，须提示补录工时）

可归集研发人工 = (total_salary + social_insurance + housing_fund) × ratio
其中分项：
  工资薪酬归集 = total_salary × ratio
  社保归集     = social_insurance × ratio
  公积金归集   = housing_fund × ratio
```

> 口径提醒：
> - 加计扣除口径：人员人工费用含"工资薪金 + 五险一金（含个人与单位，按税法口径）"，须与个税申报、社保缴纳记录一致。
> - 高企口径：科技人员（含研发）累计实际工作时间须 ≥ 183 天；研发人员费用按项目归集。
> - 若有 `non_rd_hours`，可用 `(total - non_rd_hours)` 作为研发工时近似，二选一并在表中注明方法。

## 二、明细表（按 人员 × 月份 × 项目）

| 人员 | 月份 | 项目 | 研发工时 | 总工时 | 研发占比 | 工资薪酬归集 | 社保归集 | 公积金归集 | 研发人工合计 |
|---|---|---|---|---|---|---|---|---|---|
| {{person}} | {{month}} | {{project}} | {{rd_hours}} | {{total}} | {{ratio%}} | {{salary×r}} | {{si×r}} | {{hf×r}} | {{sum}} |

> 同一人同一月跨多项目时，按各项目 `work_time.hours` 占比二次分摊到项目行。

## 三、汇总明细表（按 人员 或 按 项目）

**按人员汇总：**

| 人员 | 研发月数 | 研发总工时 | 工资薪酬归集合计 | 社保归集合计 | 公积金归集合计 | 研发人工归集合计 |
|---|---|---|---|---|---|---|

**按项目汇总（对接辅助账 / 加计归集 / 高企归集）：**

| 项目 | 参与研发人数 | 研发总工时 | 工资薪酬归集 | 社保归集 | 公积金归集 | 研发人工归集合计 | 占项目费用比 |
|---|---|---|---|---|---|---|---|

## 四、交付要求

1. 用 `run_python` 读取 `release/data/rd_expense.db`（开发态可用 `data/rd_expense.db` 或相对路径探测），不得臆造数值；缺工时/缺社保公积金列时，在表尾 `（待补）` 标注并提示补录。
2. 两表生成后写入 `output/研发人员人工费用分配明细表.md` 与 `output/研发人员人工费用分配汇总明细表.md`。
3. 汇总表的"研发人工归集合计"应等于各明细行之和（勾稽校验）。
4. 仅输出"已分摊"状态（`labor_cost.status='已分摊'`）的记录纳入正式归集；"待分摊"记录提示补录。
